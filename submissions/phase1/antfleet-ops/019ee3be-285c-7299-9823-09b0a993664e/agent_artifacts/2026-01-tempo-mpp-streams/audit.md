# Audit: 2026-01-tempo-mpp-streams

**## Missing access control on channel closure initiation**
- Location: contracts/TempoStreamChannel.sol : initiateClose
- Mechanism: The function reads the Channel but performs no check that msg.sender equals channel.payer, channel.payee, or channel.authorizedSigner before setting gracePeriodEnd.
- Impact: Any attacker can force an arbitrary channel into the grace period, preventing immediate cooperative close or further deposits until GRACE_PERIOD elapses.

**## Missing nonce and expiry validation in cooperative close**
- Location: contracts/TempoStreamChannel.sol : close
- Mechanism: After recovering the authorizedSigner, the function performs no comparison of voucher.nonce against settledNonces[voucher.channelId] and no check of block.timestamp against voucher.expiry (unlike settle).
- Impact: An attacker in possession of any previously signed voucher (including an expired one or one with a nonce already used) plus a matching payerSignature can force settlement and finalization using stale cumulativeAmount values.

**## Underflow / incorrect refund calculation possible in close when cumulativeAmount < settled**
- Location: contracts/TempoStreamChannel.sol : close
- Mechanism: delta and payerRefund are computed directly from voucher.cumulativeAmount without ensuring cumulativeAmount >= channel.settled; the subsequent safeTransfer uses the raw subtraction result.
- Impact: A malicious or malformed voucher (even if signature checks pass) causes a revert on underflow, or (if somehow bypassed) incorrect distribution of funds between payee and payer.

**## Deadline parameter accepted but never enforced in openChannel**
- Location: contracts/TempoStreamChannel.sol : openChannel
- Mechanism: The deadline argument is stored in the function signature and the DeadlineExpired error exists, but no timestamp comparison is performed before creating the channel and taking the transferFrom.
- Impact: Callers can supply an already-expired deadline with no effect; the intended time-bound protection is completely absent.

**## Anyone can add deposits to any channel**
- Location: contracts/TempoStreamChannel.sol : addDeposit
- Mechanism: The function only checks that the channel exists and is not finalized; it then executes safeTransferFrom(msg.sender, ...) with no payer-only restriction.
- Impact: An attacker can gratuitously increase any channel's deposit (using their own tokens), altering economic balances and potentially interfering with expected payer accounting or griefing channel state.
