# Audit: 2024-01-renft
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Rental order hash omits `rentalWallet`, letting a stop redirect the asset-reclaim source to an arbitrary safe
*(consensus, 6 of 6 reports)*
- Location: `smart-contracts/src/packages/Signer.sol` : `_deriveRentalOrderHash` — abused via `smart-contracts/src/policies/Stop.sol` : `stopRent` / `stopRentBatch` / `_reclaimRentedItems`
- Mechanism: The `RentalOrder` EIP-712 type string declares nine members including `address rentalWallet`, but the `abi.encode(...)` hashes only eight (`seaportOrderHash, keccak(items), keccak(hooks), orderType, lender, renter, startTimestamp, endTimestamp`) — `order.rentalWallet` is never committed. This same hash keys storage at creation (`STORE.addRentals`) and is re-derived for the existence check at stop (`STORE.removeRentals`). Because the wallet is uncommitted, a caller can supply an order byte-identical to a live one except for a substituted `rentalWallet`, and it still matches the stored hash. `Stop` then trusts the caller-supplied `order.rentalWallet` for both `ISafe(order.rentalWallet).execTransactionFromModule(... reclaimRentalOrder ...)` and the `toRentalId(order.rentalWallet)` `rentedAssets` decrement. The only backstop is `removeRentals`' underflow revert, which passes whenever the substituted safe holds the same token/id with `rentedAssets ≥ amount`.
- Impact: For a fungible ERC1155 rental, an attacker who is lender of a stoppable order (a PAY order, or a BASE order after expiry) calls `stopRent` pointing `rentalWallet` at an unrelated victim safe holding the same `(token,id)` with sufficient amount. `execTransactionFromModule` (bypassing the guard) drains the victim's units to the attacker's lender address, the decrement lands on the victim's rental ID, the real order hash is deleted, and the victim's own order becomes permanently un-stoppable (later `removeRentals` underflows). Cross-wallet asset theft plus permanent accounting corruption of a third party's rental.
- Reviewer disagreement: none — all six reports surfaced this.

## Guard `disableModule` check reads the wrong calldata word (`prevModule` instead of the module being removed)
*(consensus, 4 of 6 reports)*
- Location: `smart-contracts/src/libraries/RentalConstants.sol` : `gnosis_safe_disable_module_offset` (= `0x24`) — consumed in `smart-contracts/src/policies/Guard.sol` : `_checkTransaction` (`gnosis_safe_disable_module_selector` branch)
- Mechanism: `disableModule(address prevModule, address module)` carries the module to remove as its **second** argument (in-memory `bytes` offset `0x44`); `prevModule` is the first argument at `0x24`. The guard reads offset `0x24` and runs `_revertNonWhitelistedExtension` on it, validating the linked-list predecessor rather than the module actually being disabled. (`enableModule(address)` legitimately uses `0x24` since the module is its only argument; the disable offset should be `0x44`.)
- Impact: A rental-safe owner enables any admin-whitelisted extension `E` (the Safe prepends it: `SENTINEL → E → Stop`), then calls `disableModule(E, Stop)`. The Safe accepts it (E truly precedes Stop), and the guard checks `E` (whitelisted) instead of `Stop`, so the protocol `Stop` module is unlinked even though it is not a whitelisted/removable extension. With `Stop` gone, `_reclaimRentedItems`' `execTransactionFromModule` can never run, so `stopRent`/`stopRentBatch` revert forever: the rented NFT is frozen in the safe, escrowed payment is stuck, and the lender permanently loses reclaim ability while the renter keeps custody past term.
- Reviewer disagreement: opus-4-8 shot 3 reviewed "the Guard selector checks" and judged them sound; gpt-5.5 shot 3 did not address this path.

## OrderMetadata hash omits `orderType` and `emittedExtraData`, so neither signature binds them
*(consensus, 3 of 6 reports)*
- Location: `smart-contracts/src/packages/Signer.sol` : `_deriveOrderMetadataHash` — reachable via `Create._isValidOrderMetadata` (Seaport `zoneHash` check) and `_deriveRentPayloadHash` (CREATE_SIGNER signature)
- Mechanism: The `OrderMetadata` type string declares `uint8 orderType, uint256 rentDuration, Hook[] hooks, bytes emittedExtraData`, but the encoded preimage is only `(_ORDER_METADATA_TYPEHASH, rentDuration, keccak256(hookHashes))`. Both `orderType` and `emittedExtraData` are unbound. Because this reduced hash is what the lender's signed `zoneHash` is compared against and what the protocol signer's payload signature covers, a fulfiller can mutate `metadata.orderType` and `metadata.emittedExtraData` without invalidating either check.
- Impact: `emittedExtraData` is fully attacker-controlled at fulfillment, so the `RentalOrderStarted` event (the off-chain source of truth, since only the hash is stored) can be spoofed with arbitrary data carrying a "valid" signature — an event/off-chain-state desync. `orderType` substitution is bounded in practice because `_convertToItems` enforces mutually-exclusive structural rules (BASE / PAY / PAYEE), so a flipped type generally reverts and does not redirect settlement. Genuine EIP-712 signed-data-integrity defect; lower on-chain severity than the two above.
- Reviewer disagreement: none — the three gpt-5.5 shots did not audit this hash.

## Overlapping reward rentals can redirect previously accrued rewards
*(consensus, 3 of 6 reports)*
- Location: `smart-contracts/src/examples/revenue-share/ERC20RewardHook.sol` & `ERC1155RewardHook.sol` : `onStart` / `onStop`
- Mechanism: Reward state is keyed only by `keccak256(abi.encode(safe, token, identifier))` with a single aggregate `amount` and `lastRewardBlock`; lender attribution and split are taken from the *current* rental's decoded `RevenueShare` (`extraData`) on every accrual update. When multiple ERC1155 rentals share the same safe/token/id, a start or stop of one rental applies that caller's lender/share to rewards accrued over the entire existing `currentAmount`.
- Impact: A renter or colluding lender starts or stops a small overlapping rental for the same id and redirects rewards earned by all other active amount to an attacker-controlled lender address; in `ERC20RewardHook`, setting `lenderShare = 100` captures the full accrued slice. Theft of other lenders' accrued rewards.
- Reviewer disagreement: none explicit (the opus shots noted the example hooks in scope but did not flag this).

## Escrow credits ERC20 deposits by declared amount, not actual received balance
*(consensus, 2 of 6 reports)*
- Location: `smart-contracts/src/policies/Create.sol` : `_rentFromZone`; `smart-contracts/src/modules/PaymentEscrow.sol` : `increaseDeposit` / `_settlePayment` / `skim`
- Mechanism: `Create` records each ERC20 payment using the Seaport `items[i].amount` after execution, but `PaymentEscrow` never verifies the escrow's actual token balance delta. Fee-on-transfer, rebasing-negative, or malicious ERC20s can make the true received balance lower than the credited `balanceOf` amount; settlement later decreases the accounted balance and attempts to transfer the full nominal amount.
- Impact: Rentals paid with such tokens can become impossible to stop — settlement reverts on insufficient true escrow balance, and because `stopRent` reverts atomically, the rented NFT/ERC1155 stays locked behind the guard, unreclaimable through the normal stop path. Precondition: an order uses an ERC20 whose received amount can be less than the declared amount.
- Reviewer disagreement: three reports defended this escrow accounting code path — opus-4-8 shot 1 explicitly stated it found no issues in the deposit balance tracking / fee-skim accounting; opus-4-8 shot 2 argued pre-fee `_decreaseDeposit` with post-fee transfer correctly leaves the fee as `trueBalance - syncedBalance`; opus-4-8 shot 3 judged the escrow/storage accounting sound.

## Any single Safe owner can drain all Safe-accrued rewards
*(consensus, 2 of 6 reports)*
- Location: `smart-contracts/src/examples/revenue-share/ERC20RewardHook.sol` & `ERC1155RewardHook.sol` : `claimRewards`
- Mechanism: `claimRewards(rewardedAddress)` permits withdrawal whenever `ISafe(rewardedAddress).isOwner(msg.sender)` is true, then transfers the full reward balance directly to `msg.sender`. It neither requires a Safe transaction / threshold approval nor sends rewards to the Safe itself.
- Impact: In a multi-owner rental Safe with threshold > 1, any single owner bypasses the multisig threshold and withdraws all rewards accrued to the Safe to their own address. Precondition: the Safe has accrued rewards and the attacker controls one owner key.
- Reviewer disagreement: none explicit (gpt-5.5 shot 2 audited the same hook files for the overlapping-reward issue but did not flag `claimRewards`).

## Minority findings

## `PaymentEscrow.setFee` accepts a 100% fee numerator
*(minority, 1 of 6 reports)*
- Location: `smart-contracts/src/modules/PaymentEscrow.sol` : `setFee`
- Mechanism: `setFee` accepts `feeNumerator == 10000` (100%), which would zero out all lender/renter payouts on settlement.
- Impact: A 100% fee configuration drains all settlement value to the fee recipient, zeroing lender/renter payouts.
- Reviewer disagreement: the finding's own reporter (opus-4-8 shot 2) caveated it as `ADMIN_ADMIN`-gated and reversible — a trusted-admin misconfiguration risk rather than an attacker-reachable bug; no other report addressed this code path.

