# Audit: 2024-01-renft

# reNFT Protocol Security Audit Report

## Hook onStart/onStop status checks always return false
- Location: `Storage.sol` : `hookOnStart`, `hookOnStop`
- Mechanism: `hookOnTransaction` correctly parenthesizes the bitmask check as `(uint8(1) & hookStatus[hook]) != 0`, but `hookOnStart` and `hookOnStop` omit parentheses. Because `!=` binds tighter than `&`, both functions evaluate as `uint8(N) & (hookStatus[hook] != 0)`, i.e. a bitmask ANDed with `0` or `1`. For any non-zero status this is always `0`, so both functions always return `false` regardless of the configured bitmap.
- Impact: Any rental that includes `onStart` or `onStop` hooks fails in `Create._addHooks` and `Stop._removeHooks` with `Shared_DisabledHook`, so hook-based rental restrictions (selector allowlists, revenue sharing, wallet whitelisting, etc.) can never run. Protocols relying on hooks for security middleware are left unprotected while appearing configured.

## EIP-712 RentalOrder hash omits rentalWallet
- Location: `Signer.sol` : `_deriveRentalOrderHash`
- Mechanism: The declared EIP-712 type string for `RentalOrder` includes `address rentalWallet`, but `_deriveRentalOrderHash` hashes only `seaportOrderHash`, `items`, `hooks`, `orderType`, `lender`, `renter`, `startTimestamp`, and `endTimestamp`. `rentalWallet` is excluded from the digest even though it is part of the canonical type and is used on-chain in `Create._rentFromZone`, `Stop.stopRent`, and `Reclaimer.reclaimRentalOrder`.
- Impact: Two rental orders that differ only in `rentalWallet` produce the same protocol order hash. A caller can supply a `RentalOrder` with a substituted `rentalWallet` while keeping the same hash, causing `Stop` to reclaim assets from the wrong Safe and `Storage.removeRentals` to decrement rental IDs for the wrong recipient. This can brick rentals (guard remains active after order removal), desynchronize `rentedAssets` accounting, or redirect reclaim/settlement to unintended wallets.

## EIP-712 OrderMetadata hash omits orderType and emittedExtraData
- Location: `Signer.sol` : `_deriveOrderMetadataHash`
- Mechanism: The declared type is `OrderMetadata(uint8 orderType,uint256 rentDuration,Hook[] hooks,bytes emittedExtraData)`, but the implementation hashes only `rentDuration` and `hooks`. `orderType` and `emittedExtraData` are omitted. The same incomplete hash is embedded in `RentPayload` via `_deriveRentPayloadHash` and is compared against Seaport’s `zoneHash` in `Create._isValidOrderMetadata`.
- Impact: Multiple distinct metadata objects that differ only in `orderType` or `emittedExtraData` share the same hash and the same valid protocol signature. An attacker can reuse a CREATE_SIGNER signature while changing `orderType` in the submitted payload (e.g., BASE vs PAY vs PAYEE), altering how `_convertToItems` and `_rentFromZone` process the fulfillment. Depending on Seaport order structure and zone callback ordering, this can cause fulfillment/state-registration mismatches, failed rentals after asset movement, or unintended rental registration behavior.

## CREATE_SIGNER payload can be replayed across multiple Seaport orders
- Location: `Create.sol` : `validateOrder` / `Signer.sol` : `_deriveRentPayloadHash`
- Mechanism: The signed `RentPayload` binds `fulfillment`, `metadata`, `expiration`, and `intendedFulfiller`, but not the Seaport `orderHash`, offer contents, or consideration contents. `validateOrder` never checks that the current Seaport fulfillment corresponds to a one-time authorization. As long as the signature is unexpired, the fulfiller matches, metadata matches `zoneHash`, and execution invariants pass, the same signature can authorize additional fulfillments.
- Impact: A single protocol signature can be reused to create multiple rentals from different Seaport orders that share the same zone metadata (same duration, hooks, fulfiller, and recipient). A lender listing multiple items expecting one signature per rental can have additional rentals created without fresh protocol approval, enabling unauthorized rentals and unintended asset/payment movement.

## Guard base checks bypassed when a transaction hook is enabled
- Location: `Guard.sol` : `checkTransaction`
- Mechanism: When `STORE.contractToHook(to)` returns a hook with `hookOnTransaction` enabled, `checkTransaction` forwards to the hook and does not call `_checkTransaction`. The hook is solely responsible for enforcing rental restrictions. Example hooks in the codebase (`ERC1155RewardHook`, `ERC20RewardHook`, `WhitelistedFulfillmentHook`) implement `onTransaction` as an empty function that always succeeds.
- Impact: If a transaction hook is registered for a target contract (including an NFT collection) and the `onTransaction` bit is enabled, all default rental guard checks (blocking transfers/approvals of rented assets, blocking `setApprovalForAll`, blocking guard/module changes, etc.) are skipped for calls to that target. A renter can transfer or approve actively rented ERC-721/ERC-1155 tokens while the rental is still active, defeating the core guard purpose.

## stopRent performs irreversible actions before verifying the order exists
- Location: `Stop.sol` : `stopRent`, `stopRentBatch`
- Mechanism: `stopRent` calls `_removeHooks`, `_reclaimRentedItems`, and `ESCRW.settlePayment` before `STORE.removeRentals`, which is the only step that verifies `orders[orderHash]` is active. There is no upfront `orders[hash] == true` check. The same ordering applies in `stopRentBatch`, which performs all reclaims and hook removals in a loop before batch settlement and `removeRentalsBatch`.
- Impact: If `removeRentals` / `removeRentalsBatch` reverts (inactive order, wrong `rentalAssetUpdate` amounts causing underflow, or hash/accounting mismatch from the `rentalWallet` omission), the entire transaction reverts atomically today. However, any future change that adds partial-commit behavior, reentrancy, or non-reverting cleanup would expose double-settlement/double-reclaim risk. The ordering also allows griefers to force others to pay gas for full reclaim/settlement attempts that only fail at the final storage check.

## addRentals allows duplicate registration of the same order hash
- Location: `Storage.sol` : `addRentals`
- Mechanism: `addRentals` unconditionally sets `orders[orderHash] = true` and increments `rentedAssets[rentalId] += amount` without checking whether the order hash is already active. If `Create.validateOrder` is invoked more than once for the same derived order hash, each call stacks rental counts.
- Impact: Duplicate registration inflates `rentedAssets` counters. A subsequent single `stopRent` only decrements once, leaving positive rental counts and permanently active guard restrictions on assets that are no longer rented. Affected NFTs can become permanently untransferable from the rental Safe.

## Protocol fee can be raised after rental creation
- Location: `PaymentEscrow.sol` : `setFee`, `_settlePayment`
- Mechanism: Escrow deposits are recorded at rental creation via `increaseDeposit`, but the fee numerator is applied only at settlement in `_settlePayment` using the current `fee` value. There is no per-order fee snapshot.
- Impact: An admin (or compromised `ADMIN_ADMIN` key) can raise `fee` to an arbitrary value up to 100% immediately before `stopRent` is called, confiscating essentially all escrowed rental payments that lenders and renters expected to receive under the fee rate in effect when the rental started.

