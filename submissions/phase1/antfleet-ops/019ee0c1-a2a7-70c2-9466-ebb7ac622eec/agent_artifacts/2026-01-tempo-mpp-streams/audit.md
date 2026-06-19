# Audit: 2026-01-tempo-mpp-streams

## Unilateral cooperative close bypasses payee dispute rights
- Location: `contracts/TempoStreamChannel.sol` : `close`
- Mechanism: `close()` is documented as cooperative, but it only verifies signatures from the payer side: `channel.authorizedSigner` and `channel.payer`. It never requires approval from `channel.payee`. Since the authorized signer is controlled by the payer or their delegate, the payer can sign a low or zero cumulative voucher and immediately finalize the channel, bypassing `initiateClose()` and the grace period.
- Impact: A malicious payer can consume service, receive a valid higher-value voucher off-chain, then front-run or call `close()` with `cumulativeAmount == channel.settled` or `0`, refunding the remaining deposit to themselves and permanently blocking the payee from settling the real voucher.

## Higher-nonce low-value vouchers can invalidate valid payments
- Location: `contracts/TempoStreamChannel.sol` : `settle`
- Mechanism: Replay protection is based only on `settledNonces[channelId]`, and `settle()` is callable by anyone. The contract accepts any voucher with a nonce greater than the last settled nonce, even if its `cumulativeAmount` is lower than outstanding signed vouchers. A payer-controlled signer can create a high-nonce voucher with `cumulativeAmount == channel.settled`, submit it themselves, and advance `settledNonces` without paying anything.
- Impact: A malicious payer can invalidate previously issued lower-nonce vouchers after receiving service. Example: payee holds voucher `{nonce: 1, cumulativeAmount: 100}`; payer submits `{nonce: 2, cumulativeAmount: 0}`; the payee’s voucher is then rejected with `NonceTooLow`.

## Zero authorized signer disables signature authentication
- Location: `contracts/TempoStreamChannel.sol` : `openChannel`, `settle`, `close`
- Mechanism: `openChannel()` does not reject `authorizedSigner == address(0)`. `_recoverSigner()` returns `address(0)` for malformed signatures, including signatures with invalid length. Therefore, for channels with a zero authorized signer, arbitrary invalid signatures satisfy `signer == channel.authorizedSigner`.
- Impact: Any channel opened with a zero signer can be settled or closed without a real voucher signature. The payee, or any caller paying the payee, can drain the channel up to the deposit using fabricated vouchers.

## Anyone can force a channel into closing
- Location: `contracts/TempoStreamChannel.sol` : `initiateClose`
- Mechanism: `initiateClose()` has no caller authorization. Any external address can set `gracePeriodEnd` for any active channel, starting the one-hour close window. After the grace period, anyone can call `finalize()` and end the channel.
- Impact: A third party can grief active payment streams by forcing channels into closure, interrupting ongoing service relationships and preventing continued voucher settlement after finalization.

## Token accounting can become insolvent for fee-on-transfer or rebasing tokens
- Location: `contracts/TempoStreamChannel.sol` : `openChannel`, `addDeposit`, `settle`, `finalize`
- Mechanism: The contract records `deposit` as the requested transfer amount, not the actual token amount received. If the ERC20 charges transfer fees, rebases downward, or otherwise transfers less than requested, channel accounting overstates the contract’s backing balance. Since balances are pooled per token across channels, one channel’s settlement can consume tokens deposited for another channel.
- Impact: Payees or payers can be underpaid, settlement/finalization can revert, and funds from unrelated channels using the same token can be drained to satisfy an undercollateralized channel.

## Open-channel deadline is ignored
- Location: `contracts/TempoStreamChannel.sol` : `openChannel`
- Mechanism: `openChannel()` accepts a `deadline` parameter and defines `DeadlineExpired`, but never checks `block.timestamp > deadline`. Transactions remain valid indefinitely despite the caller supplying an expiry bound.
- Impact: A stale channel-opening transaction can be included after the payer’s intended validity window, locking funds into a channel under outdated payment terms.

