# Audit: 2024-01-renft

I have both complete reports in the prompt, so this is a merge/synthesis task — no codebase lookups are needed. Let me cross-reference the findings.

The one overlap is the rental-order-hash bug: Report A's "Rental order hash omits `rentalWallet`" and Report B's "Rental order hash does not bind the rental wallet" are the same root cause (`_deriveRentalOrderHash` dropping `order.rentalWallet`) and the same exploit path (`Stop.stopRent` trusting the caller-supplied wallet). Everything else is unique to one reviewer.

Here is the merged report:

---

# Merged Security Audit Report

## Consensus findings

## Rental order hash does not bind `rentalWallet`, allowing rented assets to be reclaimed out of an arbitrary rental safe
*(consensus — Reviewer A and Reviewer B)*
- **Location:** `smart-contracts/src/packages/Signer.sol` : `_deriveRentalOrderHash` (the `keccak256(abi.encode(...))` block). Exploited through `smart-contracts/src/policies/Stop.sol` : `stopRent` / `stopRentBatch` → `_reclaimRentedItems`, and `smart-contracts/src/packages/Reclaimer.sol` : `reclaimRentalOrder`.
- **Mechanism:** The `RentalOrder` EIP-712 type string declares nine fields including `address rentalWallet`, but the actual encoding passes only eight and **silently drops `order.rentalWallet`**:

  ```solidity
  keccak256(abi.encode(
      _RENTAL_ORDER_TYPEHASH,
      order.seaportOrderHash,
      keccak256(abi.encodePacked(itemHashes)),
      keccak256(abi.encodePacked(hookHashes)),
      order.orderType,
      order.lender,
      order.renter,
      // order.rentalWallet  <-- missing
      order.startTimestamp,
      order.endTimestamp
  ));
  ```

  The hash is the storage key (`STORE.orders[orderHash]`) and the only thing that ties a submitted `RentalOrder` back to a real rental. Because `rentalWallet` is not committed, an attacker can take a genuine, stored order and change **only** `rentalWallet` to a *different* protocol rental safe; the recomputed hash is unchanged, so `STORE.removeRentals(...)` still finds the order and succeeds. `Stop` trusts the caller-supplied `rentalWallet` both for reclaiming assets and for computing the `rentedAssets` (blocklist) decrements. Crucially, `Stop.stopRent` reclaims assets *before* the storage existence check runs, and the reclaim uses the attacker-chosen wallet:

  ```solidity
  ISafe(order.rentalWallet).execTransactionFromModule(
      address(this), 0,
      abi.encodeWithSelector(this.reclaimRentalOrder.selector, order),
      Enum.Operation.DelegateCall);
  ```

  The Stop policy is an enabled Safe module on *every* protocol rental safe, so this call succeeds against any of them. Inside `reclaimRentalOrder` (delegatecalled), the only guard is `address(this) == rentalOrder.rentalWallet`, which the substituted value satisfies, and the items are then transferred to `order.lender` (a hashed, attacker-fixed field).
- **Impact:** A lender who creates a **PAY** order (lender may stop at any time, per `_validateRentalCanBeStoped`) for a *fungible* ERC1155 token id can immediately call `stopRent` with `rentalWallet` re-pointed to any other rental safe `S_victim` that holds the same ERC1155 id. The reclaim pulls up to `item.amount` of the token out of `S_victim` and sends it to the attacker (the lender). The substitution also decrements the victim safe's rental blocklist (`rentedAssets`), leaving the genuine victim order active in storage but **no longer protected or reclaimable**, while the original renter keeps the now-de-blocklisted units — direct theft of ERC1155 balances from an unrelated rental safe. ERC721 is not vulnerable (only one address holds a given id, so the substituted wallet doesn't own it and the transfer reverts), but for BASE ERC1155 rentals after expiry *anyone* can trigger the same forced asset movement. Preconditions: overlapping ERC1155 rentals for the same token/id and a second stoppable order controlled by the attacker. Root cause is the missing `rentalWallet` in the hash; the "effects/interactions before the existence check" ordering in `stopRent` makes it reachable.

---

## Additional findings (single-reviewer)

## Safe module disable check validates the wrong address
*(Reviewer B only)*
- **Location:** `smart-contracts/src/policies/Guard.sol` : `_checkTransaction`
- **Mechanism:** The `disableModule(address prevModule,address module)` branch loads offset `0x24`, which is the `prevModule` argument, instead of the `module` being disabled. The guard therefore checks whether `prevModule` is whitelisted, not whether the target module is allowed to be disabled.
- **Impact:** A renter can enable a whitelisted extension, then call `disableModule(extension, stopPolicy)` and remove the Stop policy module from the Safe. After that, `stopRent` cannot reclaim assets via `execTransactionFromModule`, permanently blocking lender recovery of rented assets. Preconditions: at least one extension is whitelisted and can be enabled by the Safe owner.

## OrderMetadata hash omits `orderType` and `emittedExtraData`, so the server signature / Seaport `zoneHash` do not commit to them
*(Reviewer A only)*
- **Location:** `smart-contracts/src/packages/Signer.sol` : `_deriveOrderMetadataHash`
- **Mechanism:** The `OrderMetadata` type string is `OrderMetadata(uint8 orderType,uint256 rentDuration,Hook[] hooks,bytes emittedExtraData)`, but the encoding hashes only `rentDuration` and the hooks array:

  ```solidity
  keccak256(abi.encode(
      _ORDER_METADATA_TYPEHASH,
      metadata.rentDuration,
      keccak256(abi.encodePacked(hookHashes))
      // metadata.orderType and metadata.emittedExtraData omitted
  ));
  ```

  This hash is checked against the Seaport `zoneHash` (`_isValidOrderMetadata`) and is folded into the server-signed `RentPayload` digest (`_deriveRentPayloadHash`). Therefore neither the lender's Seaport order nor the `CREATE_SIGNER` signature actually binds `orderType` or `emittedExtraData`; the fulfiller supplies those values unconstrained.
- **Impact:** `emittedExtraData` is fully attacker-malleable and is emitted in `RentalOrderStarted`, so any off-chain system that trusts that event field can be fed arbitrary data for an otherwise-valid order. `orderType` is also not authenticated by the signature; in practice the structural item checks in `_convertToItems`/`_processBaseOrderOffer`/`_processPayOrderOffer` reject a mismatched type (BASE↔PAY↔PAYEE have mutually exclusive offer/consideration shapes), which blocks a straightforward order-type-confusion exploit, but the signature integrity guarantee the protocol intends (signer authorizes a *specific* order type) does not hold. Fix by including both fields (using `keccak256(emittedExtraData)` for the dynamic bytes) so the signature/zoneHash cover the full metadata.

## Later rentals can redirect accrued reward-hook rewards
*(Reviewer B only)*
- **Location:** `smart-contracts/src/examples/revenue-share/ERC20RewardHook.sol` : `onStart` / `onStop`; `smart-contracts/src/examples/revenue-share/ERC1155RewardHook.sol` : `onStart` / `onStop`
- **Mechanism:** `rentInfo` is keyed only by `(safe, token, identifier)` and aggregates all active amount, but lender and split data are not stored per rental. Each `onStart` or `onStop` accrues rewards for the entire existing `currentAmount` using the `RevenueShare` decoded from the current order's hook data.
- **Impact:** A renter or colluding lender can start or stop a small overlapping rental for the same safe/token/id and set themselves as `revenueShare.lender`; in the ERC20 hook they can also set `lenderShare` up to 100. This redirects rewards accrued for prior lenders to the attacker, who can then claim them. Preconditions: overlapping rentals for the same asset key and funded reward hooks.

## `setFee` accepts a 100% fee numerator
*(Reviewer A only)*
- **Location:** `smart-contracts/src/modules/PaymentEscrow.sol` : `setFee` (and `_calculateFee` / `_settlePayment`)
- **Mechanism:** `setFee` only rejects `feeNumerator > 10000`, so `10000` (100%) is allowed. With `fee == 10000`, every payment's `paymentAmount` becomes `amount - _calculateFee(amount) == 0`, so `_settlePaymentInFull`/`_settlePaymentProRata` transfer `0` to lender/renter while the entire payment is retained as skimmable "fee," and ERC20s that revert on zero-value transfers can brick `stopRent` for affected orders.
- **Impact:** A malicious or compromised `ADMIN_ADMIN` can confiscate 100% of all settled rent and/or block stops. Gated behind the admin role (which can already `skim`), so severity is limited to admin-trust assumptions, but admitting the boundary value is a real configuration hazard worth bounding (e.g., cap well below 10000).

---

**Merge summary:** 5 distinct findings — 1 consensus (rental-order-hash / `rentalWallet`), 4 single-reviewer (Reviewer A: OrderMetadata hash omission, `setFee` 100%; Reviewer B: Guard `disableModule` offset, reward-hook redirection). Report A's "not vulnerable" scoping notes were excluded since they describe non-findings.

