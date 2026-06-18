# Audit: 2026-01-tempo-mpp-streams

# Security Audit Report for TempoStreamChannel

## 1. Missing validation of `authorizedSigner` allows zero‑address signer and complete bypass of voucher authorization
- **Location:** `contracts/TempoStreamChannel.sol` : `openChannel` (no check), `settle` and `close` (signer comparison)
- **Mechanism:**  
  `openChannel` accepts `authorizedSigner` as a parameter and stores it in the channel without verifying that it is not `address(0)`. In `settle` and `close`, the recovered signer is compared against `channel.authorizedSigner`. If the authorized signer is set to `address(0)`, the internal `_recoverSigner` function returns `address(0)` for any invalid or malformed signature (e.g., signature length ≠ 65, or any `ecrecover` failure). The condition `signer != channel.authorizedSigner` then passes, allowing the caller to settle any voucher and drain the channel’s deposit.
- **Impact:**  
  A payer can create a channel with `authorizedSigner = address(0)` and immediately settle arbitrary vouchers, transferring the entire deposit to the payee. Alternatively, a malicious third party who observes such a channel can extract funds by submitting a deliberately invalid signature. The same bypass applies to the `close` function, enabling unilateral channel finalization with zero signer.

---

## 2. Unauthorized channel closure via voucher signature replay in `close`
- **Location:** `contracts/TempoStreamChannel.sol` : `close`
- **Mechanism:**  
  The `close` function is intended for cooperative closure where the payee signs a final voucher and the payer signs a separate closure message. However, the contract reuses the payee’s **voucher signature** (originally meant only for a single payment) as authorization to close the channel. The `close` function does **not** check the voucher’s nonce against `settledNonces`, nor does it require a fresh signature that explicitly signals “close intent”. A payer can therefore take any previously settled voucher (whose signature is already public on-chain) and call `close` with their own payer signature. The contract accepts this, finalizes the channel, and refunds the payer the remaining deposit, even though the payee never agreed to close the channel at that cumulative amount.
- **Impact:**  
  After the first on‑chain settlement, the payer can unilaterally close the channel, preventing the payee from claiming any further payments for services already rendered. The payee loses all unsettled earnings. The payer effectively steals the remaining deposit that should have been used for future streaming payments.

---

## 3. Anyone can initiate channel closure (`initiateClose` lacks access control)
- **Location:** `contracts/TempoStreamChannel.sol` : `initiateClose`
- **Mechanism:**  
  The `initiateClose` function has no `msg.sender` restriction; it can be called by any external account. It sets `channel.gracePeriodEnd = block.timestamp + GRACE_PERIOD`, starting the closure countdown. Once the grace period ends, the `finalize` function (also permissionless) can be called to distribute the remaining deposit and permanently close the channel.
- **Impact:**  
  A malicious third party can force an active channel into the grace period at any time. If the payee is unaware or does not settle all outstanding vouchers within the 1‑hour window, those vouchers become unredeemable and the payee loses the corresponding funds. This is a denial‑of‑service / griefing attack that can cause direct financial loss to the payee.

---

## 4. ECDSA signature malleability not mitigated
- **Location:** `contracts/TempoStreamChannel.sol` : `_recoverSigner`
- **Mechanism:**  
  The function uses inline assembly and `ecrecover` without enforcing that the `s` value is in the lower half of the curve order. This allows a valid signature `(r, s, v)` to be transformed into a second valid signature `(r, n–s, v^1)` that recovers the same signer address.  
- **Impact:**  
  An attacker can observe a pending `settle` transaction, create a malleable counterpart, and front‑run it. The original transaction will then fail because the nonce is no longer greater than `settledNonces`. This results in transaction griefing and denial of service for the payee, though it does not directly steal funds.
