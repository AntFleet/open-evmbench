# Audit: 2026-01-tempo-mpp-streams

Here are the vulnerabilities found in the `TempoStreamChannel` smart contract:

## Missing Access Control on `initiateClose` Allows Unrestricted Griefing/DoS
- Location: `TempoStreamChannel.sol` : `initiateClose`
- Mechanism: The `initiateClose` function lacks access control checks, allowing literally anyone to initiate the closure of any active channel. While cooperative closure requires signatures, unilateral closure via the grace period path is public. 
- Impact: An attacker or griefer can monitor the mempool for `ChannelOpened` events and immediately call `initiateClose` on newly created channels. This forces the channel into a 1-hour grace period, after which anyone can call `finalize()` to permanently close it. This repeatedly destroys streaming channels and prevents the payee and payer from maintaining long-running payment sessions, effectively causing a permanent Denial of Service (DoS) of the protocol's core utility.

## Unused `deadline` Parameter in `openChannel` Defeats Transaction Expiration Protections
- Location: `TempoStreamChannel.sol` : `openChannel`
- Mechanism: The `openChannel` function takes a `uint256 deadline` parameter, but this parameter is never actually used or checked within the function body (e.g., `if (block.timestamp > deadline) revert DeadlineExpired();`). 
- Impact: Network congestion or malicious validators could hold a user's signed `openChannel` transaction in the mempool and execute it at a much later, unfavorable time (e.g., after the payer has already decided to use a different service or channel). This breaks the core assumption of the transaction deadline protection, risking unexpected fund locking.
