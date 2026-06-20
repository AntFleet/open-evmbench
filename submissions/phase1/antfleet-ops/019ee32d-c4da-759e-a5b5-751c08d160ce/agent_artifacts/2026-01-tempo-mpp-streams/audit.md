# Audit: 2026-01-tempo-mpp-streams

An audit of the provided contract has been conducted. Below is the list of genuine security vulnerabilities found in the codebase.

## Zero-Address Bypass in Signature Verification
- Location: `TempoStreamChannel.sol` : `openChannel` & `settle`
- Mechanism: The `openChannel` function fails to validate that the `authorizedSigner` is not the zero address (`address(0)`). In the `settle` function, signature recovery is performed via `_recoverSigner`, which returns `address(0)` if it receives an invalid signature (such as a 65-byte array of zero bytes). If a channel is initialized with `authorizedSigner` set to `address(0)`, the validation `signer != channel.authorizedSigner` will evaluate to `address(0) != address(0)`, which is false, and the signature verification is successfully bypassed.
- Impact: An attacker or a malicious payee can craft a transaction to settle a voucher with a `cumulativeAmount` up to the total channel deposit using an invalid signature. This allows them to instantly drain all deposited tokens from any channel that was accidentally or maliciously incepted with `authorizedSigner` set to `address(0)`.

## Unenforced Expiration Deadline
- Location: `TempoStreamChannel.sol` : `openChannel`
- Mechanism: The `openChannel` function accepts a `deadline` parameter and identifies an unused `DeadlineExpired()` error in the contract storage; however, it lacks any validation logic to verify whether `block.timestamp <= deadline` actually holds true at the point of execution.
- Impact: Transactions to open channels can be held in the mempool by validators and executed long after their intended validity window has passed. This can result in unexpected locking of capital under volatile network conditions, or when the user no longer desires the streaming service.

## Unrestricted Channel Closure Initiation (Griefing)
- Location: `TempoStreamChannel.sol` : `initiateClose`
- Mechanism: The `initiateClose` function lacks proper access control to check if the caller (`msg.sender`) is authorized. It fails to restrict execution to either the `payer` (who owns the deposit) or the `payee` (the service provider).
- Impact: A malicious third party can arbitrarily call `initiateClose` on any active channel. This triggers the 1-hour `GRACE_PERIOD` countdown, forcing the channel into finalize-mode prematurely. This disrupts ongoing stablecoin payment streaming for AI and LLM agents and forces participants to pay gas to open new channels.
