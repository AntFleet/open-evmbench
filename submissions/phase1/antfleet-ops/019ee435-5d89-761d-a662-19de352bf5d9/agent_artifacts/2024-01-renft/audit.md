# Audit: 2024-01-renft

## Safe module disable checks the previous module instead of the module being disabled
- Location: `smart-contracts/src/policies/Guard.sol` : `_checkTransaction`
- Mechanism: For `disableModule(address prevModule,address module)`, the guard loads the address at `gnosis_safe_disable_module_offset = 0x24`, which is the `prevModule` argument, not the `module` argument. It then checks whether `prevModule` is whitelisted and never checks the actual module being disabled. A renter can enable any whitelisted extension, making it the previous module before `Stop`, then call `disableModule(extension, stopPolicy)`.
- Impact: A renter can disable the `Stop` module on a rental Safe. Future `stopRent` calls fail because `Stop` is no longer an enabled Safe module, so lenders cannot reclaim rented assets and escrow settlement/removal cannot complete.

## Rental order hashes do not bind the rental wallet
- Location: `smart-contracts/src/packages/Signer.sol` : `_deriveRentalOrderHash`
- Mechanism: The `RentalOrder` type string includes `rentalWallet`, but `_deriveRentalOrderHash()` omits `order.rentalWallet` from the encoded fields. `Storage.orders` therefore authenticates an order without authenticating which Safe holds the rented assets. `Stop.stopRent()` later trusts the caller-supplied `order.rentalWallet` for hook calls, reclaim, and rental-asset storage updates.
- Impact: An attacker can submit a valid active order with a different rental wallet. For fungible ERC1155 rentals where the attacker controls a Safe with matching active rented asset accounting, this can delete/settle another user’s order while leaving the real rented assets in the victim Safe. The victim order becomes unstoppable because `orders[hash]` has been deleted, locking assets and corrupting rental accounting.

## Fee-on-transfer ERC20s break escrow accounting
- Location: `smart-contracts/src/modules/PaymentEscrow.sol` : `increaseDeposit`, `_settlePayment`, `_safeTransfer`
- Mechanism: Escrow accounting records the nominal Seaport item amount through `increaseDeposit()` and assumes inbound/outbound ERC20 transfers move exactly that amount. Fee-on-transfer or deflationary ERC20s can deliver less than the recorded amount on deposit, or deliver less than the settled amount on withdrawal while returning success.
- Impact: Rentals using such ERC20s can become impossible to stop because escrow tries to pay more than it actually received, or recipients can be underpaid while escrow marks the full payment as settled. This creates payment loss or denial of settlement for any unsupported ERC20 accepted in orders.

## Reward hooks misattribute rewards across overlapping rentals
- Location: `smart-contracts/src/examples/revenue-share/ERC20RewardHook.sol` : `onStart`, `onStop`; `smart-contracts/src/examples/revenue-share/ERC1155RewardHook.sol` : `onStart`, `onStop`
- Mechanism: Reward state is aggregated only by `keccak256(abi.encode(safe, token, identifier))`, but lender/share data is not stored per rental. Each new `onStart()` or `onStop()` accrues rewards for the entire aggregated `currentAmount` using the lender/share decoded from that one order’s hook data.
- Impact: A user can start or stop a small overlapping rental for the same Safe/token/id with hook data favoring themselves, causing rewards earned by other active rentals in the aggregate bucket to be credited to the attacker or to the wrong party.

## Restricted selector hook state is shared only by token ID
- Location: `smart-contracts/src/examples/restricted-selector/RestrictedSelectorHook.sol` : `onStart`, `onStop`, `_isFunctionSelectorAllowed`
- Mechanism: `functionSelectorBitmap` is keyed only by `tokenId`, not by Safe and token address, and `onStop()` deletes the bitmap for that token ID unconditionally. Concurrent rentals of the same ERC1155 token ID, or same numeric ID across contexts, overwrite or delete each other’s restrictions.
- Impact: One rental can loosen or erase selector restrictions for another active rental. After a stop deletes the shared bitmap, the default bitmap is zero, which `_isFunctionSelectorAllowed()` treats as allowing all checked selectors.

