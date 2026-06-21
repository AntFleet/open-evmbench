# Audit: 2026-01-tempo-mpp-streams

## Missing zero-address check on authorizedSigner enables voucher authentication bypass
- Location: contracts/TempoStreamChannel.sol : `openChannel` / `_recoverSigner` / `settle` (also `close`)
- Mechanism: `openChannel` validates `payee` but never checks `authorizedSigner != address(0)`, so a channel can be stored with `authorizedSigner == address(0)`. `_recoverSigner` returns `address(0)` whenever `signature.length != 65`, and `ecrecover` itself returns `address(0)` for any signature with an invalid `v`/`r`/`s`. The only authentication in `settle` is `if (signer != channel.authorizedSigner) revert InvalidSigner();`. When `authorizedSigner` is zero, an attacker submits a `Voucher` with an arbitrary `cumulativeAmount` (up to `deposit`) and a deliberately malformed signature; `_recoverSigner` yields `address(0)`, the equality check passes, and the voucher settles with no valid signature at all. The recovered-address-is-zero case is never rejected, and there is no s-value malleability guard either.
- Impact: For any channel opened with a zero `authorizedSigner`, anyone can forge vouchers and drain the full deposit to the payee, completely bypassing the voucher signature scheme.

## initiateClose has no caller restriction — anyone can force-close any channel
- Location: contracts/TempoStreamChannel.sol : `initiateClose`
- Mechanism: `initiateClose` only checks that the channel exists, is not finalized, and has no active grace period; it never verifies `msg.sender == payer || msg.sender == payee`. Any external address can call it on any channel to set `gracePeriodEnd = block.timestamp + GRACE_PERIOD`. After one hour the permissionless `finalize` refunds the payer and sets `finalized = true`, permanently tearing the channel down. An attacker can do this to arbitrary active streaming channels (including immediately after `openChannel`).
- Impact: Any third party can unilaterally force-close any channel, griefing the ongoing streaming relationship and causing a payee that batches/defers settlement to lose rendered-but-unsettled value once the channel finalizes.

## close ignores voucher expiry and nonce, and the payer CLOSE authorization never expires
- Location: contracts/TempoStreamChannel.sol : `close`
- Mechanism: Unlike `settle`, `close` performs no `block.timestamp > voucher.expiry` check and no `voucher.nonce <= settledNonces[...]` check, so a voucher that `settle` would reject as expired or superseded is fully honored here. The payer's authorization is a non-EIP-712 message `keccak256(abi.encodePacked("CLOSE", channelId, cumulativeAmount))` containing no nonce, expiry, chainId, or contract address, so a payer can never revoke it and it is not domain-separated. Any `(voucher, payerSignature)` pair ever produced for a given `(channelId, cumulativeAmount)` therefore remains valid indefinitely; a counterparty holding a once-valid cooperative-close authorization (e.g., from an aborted close negotiation) can apply it at an arbitrary later time as long as `cumulativeAmount >= channel.settled`.
- Impact: A stale/expired voucher plus a previously signed, non-expiring CLOSE authorization can be replayed to finalize a channel at an unintended time and split — letting a counterparty bank an over-authorized payout after far less service was actually delivered.

## Deposit accounting uses requested amount, not received balance (fee-on-transfer/rebasing drift)
- Location: contracts/TempoStreamChannel.sol : `openChannel` / `addDeposit`
- Mechanism: Both functions record `channel.deposit = deposit` / `channel.deposit += amount` using the requested amount rather than the actual balance delta credited by `safeTransferFrom`. The contract accepts any `IERC20`; for a fee-on-transfer or rebasing token the contract receives less than `deposit`, yet vouchers may be settled up to the recorded `deposit`. Because all channels share one token balance, the inflated accounting lets a channel's settlements/`finalize`/`close` either revert from insufficient balance or be paid out of other channels' funds.
- Impact: With non-standard (fee-on-transfer/rebasing) tokens, a channel becomes over-collateralized on paper, causing reverting settlements/refunds (locked funds) or cross-channel fund drainage.

## deadline parameter accepted but never enforced in openChannel
- Location: contracts/TempoStreamChannel.sol : `openChannel`
- Mechanism: `openChannel` takes a `deadline` argument and the contract declares a `DeadlineExpired` error, but `deadline` is never compared against `block.timestamp` (the `if (block.timestamp > deadline) revert DeadlineExpired();` guard is absent). The documented stale-transaction protection does not exist.
- Impact: A pending `openChannel` can be mined arbitrarily late; any client/integrator relying on the advertised deadline guard for transaction-freshness has no protection (no direct theft, since the caller funds their own channel).

