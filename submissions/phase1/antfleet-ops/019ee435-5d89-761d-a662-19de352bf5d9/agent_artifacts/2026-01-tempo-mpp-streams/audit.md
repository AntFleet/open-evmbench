# Audit: 2026-01-tempo-mpp-streams

## Payer can unilaterally bypass the grace period with `close`
- Location: `contracts/TempoStreamChannel.sol` : `close`
- Mechanism: `close` is documented as cooperative, but it verifies only payer-controlled authorization: a voucher from `authorizedSigner` and a `payerSignature`. Since the authorized signer is the payer or payer delegate, the payer can sign a low cumulative amount, sign the close message, and finalize immediately. There is no payee signature, payee caller check, nonce check, expiry check, or grace-period requirement.
- Impact: A malicious payer can receive service, then close the channel at `channel.settled` or another low amount before the payee settles their latest voucher. The payer receives the remaining refund and the payee’s unpaid vouchers become permanently unusable.

## Zero `authorizedSigner` lets invalid voucher signatures settle funds
- Location: `contracts/TempoStreamChannel.sol` : `openChannel`, `_recoverSigner`, `settle`
- Mechanism: `openChannel` does not reject `authorizedSigner == address(0)`. `_recoverSigner` returns `address(0)` for malformed signatures, including non-65-byte signatures or failed `ecrecover`. `settle` only checks `signer == channel.authorizedSigner`, so a zero-signer channel accepts arbitrary invalid signatures as valid voucher authorization.
- Impact: If a payer is tricked into opening a channel with `authorizedSigner = address(0)`, a malicious payee or colluding caller can settle any cumulative amount up to the full deposit without a real payer signature, draining the channel to the payee.

## Higher-nonce low-value vouchers can invalidate unpaid payee vouchers
- Location: `contracts/TempoStreamChannel.sol` : `settle`
- Mechanism: `settle` requires only `voucher.nonce > settledNonces[channelId]` and then stores that nonce, even if `voucher.cumulativeAmount` is merely equal to the already-settled amount. Because settlement is permissionless and vouchers are signed by the payer-side signer, the payer can submit a higher-nonce, zero-delta voucher before the payee settles an earlier higher-value voucher.
- Impact: A payer can make the payee’s valid unpaid voucher revert with `NonceTooLow`, permanently denying payment for already-provided service.

## Anyone can force channels into the close countdown
- Location: `contracts/TempoStreamChannel.sol` : `initiateClose`
- Mechanism: `initiateClose` has no caller authorization. Any address can set `gracePeriodEnd` for any active channel, starting the one-hour close countdown. After the period, anyone can call `finalize` and end the channel.
- Impact: Attackers can prematurely terminate active streaming payment channels. Payees must notice and settle within the forced window; otherwise finalization refunds the remaining deposit to the payer and prevents later voucher settlement.

