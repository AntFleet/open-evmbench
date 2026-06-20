# Audit: 2024-01-renft

## Reentrancy in Rental Stop Flow
- Location: smart-contracts/src/policies/Stop.sol : stopRent (and stopRentBatch)
- Mechanism: stopRent performs external calls to hooks (`_removeHooks` -> `IHook.onStop`), the rental safe (`_reclaimRentedItems` via `execTransactionFromModule` + delegatecall into `Reclaimer.reclaimRentalOrder`), and `PaymentEscrow.settlePayment` (which does ERC20 `transfer` calls) *before* calling `STORE.removeRentals` to delete the order hash and rental asset state. No reentrancy guard exists, and the rental order remains valid in storage (so `_validateRentalCanBeStoped` still passes) during these calls.
- Impact: An attacker controlling a hook, a malicious ERC20 used in payment settlement, or a reentrant token transfer can re-enter `stopRent` (or `stopRentBatch`) for the same `RentalOrder`, causing duplicate asset reclamation from the rental safe and/or duplicate payment settlement from the escrow (double-spend of lender/renter payouts).

## Unauthorized Hook Invocation on Rental Start
- Location: smart-contracts/src/policies/Create.sol : _addHooks (called from _rentFromZone)
- Mechanism: `_addHooks` only checks `STORE.hookOnStart(target)` (a bitmap flag) before calling `IHook.onStart`, but any address can be supplied in `OrderMetadata.hooks` by the order signer; the bitmap is set via `Guard.updateHookStatus` (ADMIN role only) but there is no check that the hook target was previously registered or that `itemIndex` points to a valid rental item.
- Impact: A malicious CREATE_SIGNER (or compromised signer key) can include a hook that performs arbitrary state changes or reentrancy during rental creation, even if the hook was never intended to be active for the protocol.

## Missing Validation of Rental Order Immutability After Signature
- Location: smart-contracts/src/policies/Create.sol : _rentFromZone (and _isValidOrderMetadata)
- Mechanism: The zone hash check only verifies `keccak256(metadata)` against the Seaport zoneHash; `RentPayload` (containing `fulfillment.recipient`, `expiration`, and `intendedFulfiller`) is signed but the resulting `RentalOrder` is constructed from live Seaport data after fulfillment, with no binding of the signed payload hash to the final on-chain rental order hash stored in `STORE`.
- Impact: A CREATE_SIGNER signature can be reused or front-run to start a rental with different effective parameters (different safe recipient or duration) than what the signer intended, or an attacker can snipe a signed payload intended for a specific fulfiller.

## Incorrect Fee Accounting on Early PAY Order Stop
- Location: smart-contracts/src/modules/PaymentEscrow.sol : _settlePayment (and _settlePaymentProRata)
- Mechanism: When `orderType == PAY` and the order is stopped early, the fee is computed on the full `item.amount` and subtracted to produce `paymentAmount`, but `_decreaseDeposit` always subtracts the original `item.amount`; the skim logic later assumes the delta between true balance and `balanceOf` represents only protocol fees.
- Impact: Protocol fees can be under- or over-collected on early-terminated PAY orders (lender/renter receive incorrect net amounts), and an admin can skim more (or less) than the intended protocol fee by manipulating timing of stops.

## Delegatecall Context Confusion in Reclaimer
- Location: smart-contracts/src/packages/Reclaimer.sol : reclaimRentalOrder
- Mechanism: The function checks `address(this) != original` and `address(this) == rentalOrder.rentalWallet` but is always reached via delegatecall from a rental safe (enabled as a Stop module); the `original` address is an immutable set at construction of the Stop policy itself.
- Impact: An attacker who obtains a delegatecall path to Reclaimer (via a whitelisted delegate or compromised extension) can pass an arbitrary `RentalOrder` whose `rentalWallet` field matches the calling context, allowing unauthorized extraction of any assets the safe currently holds.
