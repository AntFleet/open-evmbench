# Audit: 2026-01-tempo-mpp-streams

## Authorized signer zero-address allows voucher forgery
- Location: `TempoStreamChannel.sol` : `openChannel`
- Mechanism: `openChannel` accepts `authorizedSigner` without any zero-address validation. In `settle` and `close`, the recovered signer is compared with `channel.authorizedSigner` using `!=`. `_recoverSigner` returns `address(0)` for malformed signatures (and `ecrecover` returns `address(0)` for invalid `v`/`r`/`s`). If a payer (or anyone opening a channel) sets `authorizedSigner = address(0)`, any caller can submit an invalid/garbage signature, recover `address(0)`, and pass the `signer != channel.authorizedSigner` check.
- Impact: The payee (or any attacker coordinating with them) can forge vouchers for arbitrary `cumulativeAmount` up to the full deposit and drain the entire channel deposit to `payee` without the payer's authorized signer ever signing anything.

## `deadline` parameter is accepted but never enforced
- Location: `TempoStreamChannel.sol` : `openChannel`
- Mechanism: `openChannel` takes a `deadline` argument and even declares `error DeadlineExpired()`, but the function never checks `block.timestamp <= deadline`. The `DeadlineExpired` error is never used anywhere in the contract.
- Impact: Users relying on the deadline for inclusion guarantees (e.g., to avoid having their `safeTransferFrom` pulled at an unfavorable time, or to prevent stale channel opens from being mined much later) have no protection. A signed/approved open can be executed indefinitely past the intended deadline.

## `initiateClose` has no access control
- Location: `TempoStreamChannel.sol` : `initiateClose`
- Mechanism: `initiateClose` only verifies the channel exists, is not finalized, and has no active grace period. It does not check that `msg.sender` is the `payer`, `payee`, or `authorizedSigner`. Anyone can call it on any open channel.
- Impact: A griefing attacker can force any active streaming channel into the closure grace period at any time. The payee is then pressured to settle all outstanding vouchers within `GRACE_PERIOD` (1 hour) or forfeit unpaid streaming revenue, and the payer's channel is forcibly wound down. This breaks the assumption that closure is payer-controlled.

## `addDeposit` has no access control
- Location: `TempoStreamChannel.sol` : `addDeposit`
- Mechanism: `addDeposit` only checks the channel exists, is not finalized, and `amount != 0`. It does not verify `msg.sender == channel.payer`. It pulls `amount` from `msg.sender` via `safeTransferFrom` and increments `channel.deposit`.
- Impact: Any account that has approved the contract can deposit into another party's channel. While the funds ultimately flow to `payer` (via refund) or `payee` (via settlement), this violates the intended payer-only top-up semantics and lets a third party manipulate `channel.deposit` accounting (e.g., to alter `getAvailableBalance` readings or interfere with expected refund amounts), and it makes the unused-`deadline` / front-running surface worse since deposits can be injected by non-owners.

## `close` skips nonce and expiry validation on the voucher
- Location: `TempoStreamChannel.sol` : `close`
- Mechanism: Unlike `settle`, the cooperative `close` path never checks `block.timestamp > voucher.expiry` (no `VoucherExpired` revert) and never compares `voucher.nonce` against `settledNonces[voucher.channelId]`. It only verifies the voucher signature is from `authorizedSigner` and that the payer signed a `CLOSE channelId cumulativeAmount` message. The `CLOSE` digest also binds only `channelId` and `cumulativeAmount` — not nonce, expiry, or token.
- Impact: An expired voucher, or a voucher whose nonce is below the last settled nonce, can still be used in a cooperative close. Because both payer and authorized signer have signed, severity is limited, but a payer's `CLOSE` signature for a given `cumulativeAmount` is reusable with any voucher of the same amount (including expired/stale ones) since the close hash has no nonce/expiry binding, undermining the replay-protection guarantees that `settle` enforces.

## `close` pays payee even when `delta` exceeds the remaining channel balance
- Location: `TempoStreamChannel.sol` : `close`
- Mechanism: `close` computes `delta = voucher.cumulativeAmount - channel.settled` and only guards the payee transfer with `delta <= channel.deposit` (not `delta <= channel.deposit - channel.settled`). The payer refund is `channel.deposit - voucher.cumulativeAmount`, which reverts on underflow when `cumulativeAmount > deposit`, so catastrophic overpayment is currently blocked by the refund revert — but the payee-side guard is logically wrong: it permits any `delta` up to the full `deposit` regardless of how much has already been paid out via prior `settle` calls.
- Impact: If the refund arithmetic were ever relaxed (or via a token that returns `true` regardless), the contract would overpay `payee` and under-refund `payer`. As written it manifests as confusing revert behavior rather than direct loss, but the accounting check is incorrect and should be `delta <= channel.deposit - channel.settled` to match `settle`'s invariant.
