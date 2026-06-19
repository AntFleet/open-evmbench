# Audit: 2026-01-tempo-mpp-streams

## Missing Deadline Validation in openChannel
- Location: `contracts/TempoStreamChannel.sol` : `openChannel`
- Mechanism: The `openChannel` function accepts a `deadline` parameter intended to bound the transaction's validity period and protect against stale executions, but it never validates `block.timestamp` against this `deadline`. The parameter is completely ignored in the function logic.
- Impact: Users are exposed to stale transaction execution. If network congestion delays the transaction or if it is held in the mempool, it can be mined long after the user's intended deadline, potentially locking their funds into a payment channel when their intentions or external conditions have changed.

## Missing Access Control in initiateClose
- Location: `contracts/TempoStreamChannel.sol` : `initiateClose`
- Mechanism: The `initiateClose` function lacks any authorization checks to verify that the caller is either the `payer` or the `payee` of the channel. Any arbitrary external address can call this function and start the grace period for any active channel.
- Impact: An attacker can grief users by force-closing their active streaming payment channels. This causes a Denial of Service for the ongoing machine-to-machine service (e.g., LLM inference) and forces the parties to incur additional gas costs and downtime to open a replacement channel.

## Grace Period Bypass in settle Function
- Location: `contracts/TempoStreamChannel.sol` : `settle`
- Mechanism: The `settle` function verifies that the channel is not finalized and the voucher hasn't expired, but it fails to check if the current `block.timestamp` has exceeded `channel.gracePeriodEnd`. This allows settlements to occur even after the grace period has concluded, provided the `finalize()` function has not yet been successfully called.
- Impact: The payee can continue to submit and settle vouchers after the grace period has expired. If the payer is slow to call `finalize()`, or if the payee actively front-runs the payer's finalization transaction in the mempool with a late settlement, the payee can extract additional funds, completely undermining the dispute-resolution guarantees of the channel's grace period.
