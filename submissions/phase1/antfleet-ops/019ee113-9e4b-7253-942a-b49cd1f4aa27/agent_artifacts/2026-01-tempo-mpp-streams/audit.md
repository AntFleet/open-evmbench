# Audit: 2026-01-tempo-mpp-streams

# TempoStreamChannel Security Audit

## Authorized signer zero-address bypasses signature verification
- **Location:** `TempoStreamChannel.sol` : `openChannel`, `settle`, `close`
- **Mechanism:** `openChannel` validates that `payee != address(0)` but performs no check on `authorizedSigner`. The custom `_recoverSigner` helper returns `address(0)` whenever `ecrecover` fails — which it does for any signature with an out-of-range `v` (e.g. `v = 0`), with `r = 0` or `s = 0`, or with a 65-byte buffer of zeros. In `settle` (and similarly in `close`), the gate is `if (signer != channel.authorizedSigner) revert InvalidSigner()`. If a payer mistakenly (or via a malicious UI default) opens a channel with `authorizedSigner = address(0)`, then `_recoverSigner(digest, garbageSignature)` returns `address(0)` and the equality holds, so the voucher signature check is silently bypassed.
- **Impact:** Anyone can call `settle` (or `close`) with a junk 65-byte signature and drain the entire channel deposit to the payee — no participation from the authorized signer is required. The payee (or a payee colluding with the caller) can sweep the full `channel.deposit` in a single transaction, completely losing the payer's funds. The fix is to add `if (authorizedSigner == address(0)) revert ZeroAddress();` in `openChannel` (and ideally use OpenZeppelin's `ECDSA.recover` which validates `v ∈ {27,28}` and `s` range).

---

## `initiateClose` has no access control — anyone can start the grace period
- **Location:** `TempoStreamChannel.sol` : `initiateClose`
- **Mechanism:** `initiateClose` only checks that the channel exists, is not finalized, and is not already in a grace period. It does not check `msg.sender == channel.payer` (or any authorized role). A third party can call it on any live channel and set `channel.gracePeriodEnd = block.timestamp + GRACE_PERIOD`.
- **Impact:** A griefing / denial-of-service vector against the payee: a malicious third party can force the channel into its 1-hour wind-down window. If the payee is slow, asleep, or has a high-latency voucher-submission pipeline, the window can close before they can submit a final voucher, after which `finalize` (also permissionless) refunds the remainder to the payer and the payee loses any unsettled cumulative amount. The same front-runnable call also forces a payer who wanted to keep the channel open into an unwanted close countdown. The function should require `msg.sender == channel.payer` (or at minimum disallow arbitrary third parties).

---

## `close()` does not check voucher expiry — stale/expired vouchers are accepted
- **Location:** `TempoStreamChannel.sol` : `close`
- **Mechanism:** `settle` explicitly enforces `if (block.timestamp > voucher.expiry) revert VoucherExpired()`, but the cooperative `close` path performs no expiry check on the supplied `Voucher`. It only verifies the EIP-712 signature and the payer's personal_sign over `(channelId, cumulativeAmount)`. Any voucher — including one whose `expiry` is years in the past — is accepted as the "final" settlement.
- **Impact:** If a payer's key (or a delegated authorized signer key) is compromised after the intended voucher has expired, or if the payer signs a `close` personal-sign message carelessly without re-checking the voucher's freshness, the payee can pair that personal-sign with any old expired voucher (matching the signed `cumulativeAmount`) and finalize the channel. This decouples the on-chain finalization from the freshness guarantees the payer thought they had. The fix is to mirror the `settle` check: `if (block.timestamp > voucher.expiry) revert VoucherExpired();`.

---

## `close()` does not enforce or update voucher nonce
- **Location:** `TempoStreamChannel.sol` : `close`
- **Mechanism:** Unlike `settle`, which enforces `voucher.nonce > settledNonces[channelId]` and then writes the new nonce, `close` ignores the nonce entirely — it never reads `settledNonces` and never updates it. The only arithmetic guard is the implicit underflow check in `delta = voucher.cumulativeAmount - channel.settled` and `payerRefund = channel.deposit - voucher.cumulativeAmount`.
- **Impact:** The payee (who holds the payer-signed `close` message) can reuse the same EIP-712-signed voucher across channels or replay an old voucher whose `cumulativeAmount` is in `(channel.settled, channel.deposit]` as a `close` settlement. While the underflow in the refund computation prevents the trivial "double-pay" to the payee, the missing nonce accounting means the protocol's replay-protection invariant (one voucher → one settlement) is broken on the `close` path, and downstream off-chain accounting/reconciliation that relies on nonces will be desynchronized. Add the same `nonce > settledNonces` check and update `settledNonces` at the end of `close`.

---

## `openChannel` accepts but never validates the `deadline` parameter
- **Location:** `TempoStreamChannel.sol` : `openChannel`
- **Mechanism:** The function signature includes `uint256 deadline` (a classic EIP-2612 / permit-style replay/replay-protection parameter), but the body never executes `if (block.timestamp > deadline) revert DeadlineExpired();` — the contract even defines a `DeadlineExpired` error that is never used. The parameter is effectively a dead argument.
- **Impact:** Integrators who pass a deadline (e.g. from a meta-transaction relayer or a frontend flow that computes "valid for 10 minutes") believe the channel open is bounded in time. In reality the transaction remains valid indefinitely, so a permissioned/long-lived signed intent to open a channel can be executed at any future time — potentially long after the payer's pricing, payee identity, or authorized-signer set has changed. The function should enforce `if (block.timestamp > deadline) revert DeadlineExpired();`.

---

## Custom `_recoverSigner` lacks EIP-2 / OpenZeppelin-style malleability and `v` checks
- **Location:** `TempoStreamChannel.sol` : `_recoverSigner` (used by `settle` and `close`)
- **Mechanism:** The helper extracts `r, s, v` from the 65-byte buffer and calls `ecrecover` directly with no validation: it does not check `v ∈ {27, 28}`, does not check `s` is in the lower half of the secp256k1 group order (EIP-2), and does not reject `r == 0` / `s == 0`. This is a strict subset of OpenZeppelin's `ECDSA.recover` protections.
- **Impact:** Two consequences. (1) Combined with the zero-address `authorizedSigner` issue above, the lack of `v` validation is what makes the signature bypass possible. (2) Even with a non-zero `authorizedSigner`, signature malleability (flipping `s` to `n - s` and recomputing `v`) produces a second valid `(r,s,v)` tuple for the same digest and signer. In `settle` the nonce check prevents the malleated signature from re-settling, but the off-chain voucher is now "consumed" only by the original signature, leaving the malleated form a latent footgun for any future code path that drops the nonce check (such as `close`). Use OpenZeppelin's `ECDSA.recover` (or replicate its `s` and `v` checks) and consider EIP-2098 compact signatures.

---

## `addDeposit` lacks payer-only access control
- **Location:** `TempoStreamChannel.sol` : `addDeposit`
- **Mechanism:** `addDeposit` checks only that the channel exists, is not finalized, and `amount != 0`. It does not require `msg.sender == channel.payer`. Any external account can `safeTransferFrom` themselves (or, more interestingly, force a `transferFrom` if the payer previously granted an allowance to the contract) and inflate `channel.deposit`. It is also a reentrancy-adjacent hazard because `channel.deposit += amount` is written *after* the external `safeTransferFrom` (mitigated only by `nonReentrant`).
- **Impact:** Lower severity, but it (a) breaks the implicit "only payer can fund this channel" invariant that the comment and event names suggest, and (b) creates a surprising griefing surface — a third party can force a payer who approved this contract to spend allowance on a channel the payer may have intended to abandon, since `settle`/`finalize` accounting is driven by `channel.deposit`. Recommend `if (msg.sender != channel.payer) revert UnauthorizedCaller();` and applying checks-effects-interactions (write `channel.deposit` before the external call).

---

## No balance-vs-accounting reconciliation — unsafe with fee-on-transfer / rebasing tokens
- **Location:** `TempoStreamChannel.sol` : `openChannel`, `addDeposit`, `settle`, `close`, `finalize`
- **Mechanism:** All deposit/settlement accounting uses the *argument* amount (`channel.deposit`, `voucher.cumulativeAmount`, `delta`) rather than the contract's actual ERC-20 balance change. There is no snapshot of `IERC20(token).balanceOf(this)` before/after a transfer. TIP-20 is the target, but the contract is typed as `IERC20` and accepts arbitrary tokens.
- **Impact:** If a non-TIP-20 token with a transfer fee (e.g. PAXG-style fee-on-transfer) or a rebasing supply (e.g. OHM-style, or stETH rebases) is supplied, the contract's tracked `channel.deposit` will exceed the actual tokens it holds, and `settle`/`finalize` will revert when trying to pay out the "accounted" total. Worse, the `InsufficientDeposit` check in `settle` is computed against `channel.deposit`, not the real balance, so a partial-fill transfer can pass the guard and the subsequent `safeTransfer` will fail and revert the whole settlement. Either explicitly reject non TIP-20 tokens, or store balances via `balanceOf` deltas.
