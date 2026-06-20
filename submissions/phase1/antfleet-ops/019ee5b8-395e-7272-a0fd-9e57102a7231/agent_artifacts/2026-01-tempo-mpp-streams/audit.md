# Audit: 2026-01-tempo-mpp-streams

Found 5 genuine vulnerabilities in the supplied contract.

## Cooperative close can be executed without payee consent
- Location: `contracts/TempoStreamChannel.sol` : `close`
- Mechanism: `close()` is documented as requiring both parties to agree, but it only verifies `signature` from `channel.authorizedSigner` and `payerSignature` from `channel.payer`. The payee never signs or authorizes the close. Since `authorizedSigner` is payer-controlled by design, the payer can produce both required signatures for any low cumulative amount.
- Impact: A malicious payer can consume service, then immediately finalize the channel with a lower voucher, refunding the rest to themselves and permanently blocking the payee from settling a valid higher outstanding voucher.

## Higher nonce can invalidate higher-value unpaid vouchers
- Location: `contracts/TempoStreamChannel.sol` : `settle`
- Mechanism: Settlement rejects any voucher with `voucher.nonce <= settledNonces[channelId]`, but it does not require the nonce ordering to correspond to increasing `cumulativeAmount`. A payer-controlled signer can issue or submit a higher-nonce voucher with the current or lower owed amount, causing `settledNonces` to advance while paying little or nothing.
- Impact: The payer can front-run or preempt the payee’s real voucher. Example: payee holds `nonce=10, cumulative=100`; payer submits `nonce=11, cumulative=0/1`; the contract records nonce 11 and the payee’s voucher is now permanently rejected.

## Zero authorized signer bypasses signature authorization
- Location: `contracts/TempoStreamChannel.sol` : `openChannel`, `settle`, `_recoverSigner`
- Mechanism: `openChannel()` does not reject `authorizedSigner == address(0)`. `_recoverSigner()` returns `address(0)` for malformed signatures, and `settle()` only checks `signer == channel.authorizedSigner`. Therefore, channels opened with a zero signer accept invalid signatures as authorized.
- Impact: For any such channel, anyone can submit an arbitrary voucher with a malformed signature and settle up to the full deposit to the payee without payer authorization.

## Anyone can force a channel into closure
- Location: `contracts/TempoStreamChannel.sol` : `initiateClose`
- Mechanism: `initiateClose()` has no caller check. Any address can set `gracePeriodEnd` on any active channel, and there is no way to cancel or reset the closing state.
- Impact: A third party can grief active payment channels by forcing them into the grace-period shutdown path, after which the channel can be finalized and can no longer be used for ongoing streaming payments.

## Channel-open deadline is ignored
- Location: `contracts/TempoStreamChannel.sol` : `openChannel`
- Mechanism: `openChannel()` accepts a `deadline` parameter and defines `DeadlineExpired`, but never checks `block.timestamp > deadline`.
- Impact: A signed or submitted channel-open transaction can execute after the payer’s intended validity window, potentially opening and funding a stale payment channel after off-chain terms, pricing, or service availability have changed.

