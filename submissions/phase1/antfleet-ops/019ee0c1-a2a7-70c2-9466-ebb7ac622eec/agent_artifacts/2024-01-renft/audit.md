# Audit: 2024-01-renft

## Malicious ERC20 tips can permanently block rental stops
- Location: `smart-contracts/src/policies/Create.sol` : `_convertToItems`, `_rentFromZone`; `smart-contracts/src/modules/PaymentEscrow.sol` : `settlePayment`
- Mechanism: Seaport allows fulfillers to append extra consideration items as tips, but `Create` treats the entire `zoneParams.consideration` array as signed rental payment data. A fulfiller can append a malicious ERC20 tip to the escrow recipient; `ESCRW.increaseDeposit` records it as an escrowed payment, and later `settlePayment` must transfer it during `stopRent`.
- Impact: The malicious ERC20 can revert or return false on payout, causing every stop attempt for that rental to revert. The rented asset and legitimate escrowed payments remain locked.

## `setFallbackHandler` is not blocked by the Safe guard
- Location: `smart-contracts/src/policies/Guard.sol` : `_checkTransaction`
- Mechanism: The guard blocks `setGuard`, module changes, token approvals, and token transfers, but it does not block Gnosis Safe `setFallbackHandler(address)`. A renter can set the Safe fallback handler to the rented token contract, then call the Safe with ERC721/ERC1155 transfer calldata. The Safe fallback forwards the calldata to the token with the Safe as caller.
- Impact: A renter can transfer rented ERC721/ERC1155 assets out of the rental Safe, bypassing the guard and stealing the lender’s asset.

## ERC1155 rentals can be moved during receipt before registration
- Location: `smart-contracts/src/policies/Create.sol` : `validateOrder`, `_rentFromZone`; `smart-contracts/src/policies/Guard.sol` : `_checkTransaction`
- Mechanism: ERC1155 assets are transferred into the rental Safe before `Create._rentFromZone` calls `STORE.addRentals`. The ERC1155 `safeTransferFrom` triggers the Safe’s receiver/fallback path while `STORE.isRentedOut` is still false. A malicious renter-controlled fallback handler can reenter the Safe and execute a transfer of the just-received ERC1155 before the rental is registered.
- Impact: A renter can steal ERC1155 assets during rental creation; subsequent protocol state may record a rental for an asset no longer held by the Safe.

## Rental order hashes do not bind the rental Safe
- Location: `smart-contracts/src/packages/Signer.sol` : `_deriveRentalOrderHash`; `smart-contracts/src/policies/Stop.sol` : `stopRent`, `stopRentBatch`
- Mechanism: The `RentalOrder` type string includes `rentalWallet`, but `_deriveRentalOrderHash` omits `order.rentalWallet` from the encoded hash. `Stop` then trusts the caller-supplied `rentalWallet` for both `execTransactionFromModule` reclaim and `rentedAssets` decrements.
- Impact: An attacker can take a valid stored order and submit it with a different rental Safe. For overlapping ERC1155 token IDs, this lets the attacker pull tokens from an unrelated victim Safe to the order’s lender and corrupt the victim’s rental accounting.

## `stopRent` reclaims assets before proving the order exists
- Location: `smart-contracts/src/policies/Stop.sol` : `stopRent`, `stopRentBatch`
- Mechanism: `stopRent` performs hooks, reclaims rented assets, and settles escrow before `STORE.removeRentals` checks that the derived order hash exists. Combined with reusable protocol signatures that are not bound to a specific Seaport order and the malformed rental hash, an attacker can submit a not-yet-existing PAY order, receive the victim asset, create the matching order during the receiver callback, and let the final storage removal succeed.
- Impact: A malicious actor can steal actively rented NFTs from victim Safes and leave the victim rentals/payment escrow in an unrecoverable or frozen state.

## Empty or incomplete Seaport executions bypass asset-transfer invariants
- Location: `smart-contracts/src/policies/Create.sol` : `_executionInvariantChecks`, `_rentFromZone`
- Mechanism: `_executionInvariantChecks` only iterates over `totalExecutions` and verifies recipients for executions that Seaport reports. It does not prove that every offer/consideration item used to build the rental was actually transferred. If Seaport matching nets transfers out so `totalExecutions` is empty or incomplete, the loop passes while `STORE.addRentals` and `ESCRW.increaseDeposit` still record the rental and payment amounts.
- Impact: An attacker can create fake rentals with no corresponding token/payment transfer, then stop them to drain real ERC20 balances already held by the escrow.

## Partial fills can collide on one rental order hash
- Location: `smart-contracts/src/packages/Signer.sol` : `_deriveRentalOrderHash`; `smart-contracts/src/modules/Storage.sol` : `addRentals`, `removeRentals`
- Mechanism: The rental storage key is a bool keyed by the derived rental order hash. For partial Seaport fills with the same `seaportOrderHash`, same partial item amounts, same Safe, and same timestamp, multiple fills can derive the same rental order hash. `addRentals` only sets `orders[hash] = true`, while rented asset amounts accumulate.
- Impact: The first stop deletes the shared order hash and removes only one fill’s amount. Later stops revert with `OrderDoesNotExist`, locking the remaining rented assets and ERC20 settlement.

## `disableModule` checks the wrong Safe module argument
- Location: `smart-contracts/src/policies/Guard.sol` : `_checkTransaction`
- Mechanism: For `disableModule(address prevModule,address module)`, the guard loads offset `0x24`, which is `prevModule`, and checks whether that address is whitelisted. It should validate the `module` being disabled. A renter can enable a whitelisted extension so it becomes the previous module, then call `disableModule(extension, stopPolicy)`.
- Impact: The renter can disable the Stop policy module from the rental Safe. Future `stopRent` calls cannot reclaim assets through `execTransactionFromModule`, causing lender asset recovery to fail.

## Reward hooks misattribute rewards across overlapping rentals
- Location: `smart-contracts/src/examples/revenue-share/ERC20RewardHook.sol` : `onStart`, `onStop`; `smart-contracts/src/examples/revenue-share/ERC1155RewardHook.sol` : `onStart`, `onStop`
- Mechanism: `rentInfo` is keyed only by `(safe, token, identifier)` and aggregates amount/last block across all overlapping rentals. The lender and split are taken from the current hook call’s `extraData`, so accruing rewards for the whole aggregate amount uses whichever lender/share is supplied by the latest start or stop.
- Impact: A renter or colluding lender can start/stop a small overlapping rental for the same asset key and redirect rewards accrued for other lenders to themselves.

