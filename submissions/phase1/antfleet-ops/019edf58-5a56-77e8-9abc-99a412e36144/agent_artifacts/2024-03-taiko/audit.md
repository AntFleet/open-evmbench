# Audit: 2024-03-taiko

## TaikoTimelockController admin can bypass timelock delay
- Location: `TaikoTimelockController.sol` : `getMinDelay()`
- Mechanism: `getMinDelay()` returns `0` when the caller has `TIMELOCK_ADMIN_ROLE`. `TimelockControllerUpgradeable.schedule()` uses `getMinDelay()` to compute the operation ready timestamp (`block.timestamp + getMinDelay()`). Since the admin (owner) can also grant themselves `PROPOSER_ROLE` and `EXECUTOR_ROLE`, they can schedule an operation with zero delay and execute it in the same transaction.
- Impact: Any governance action can be executed immediately by the timelock admin, completely defeating the timelock security mechanism. If the admin key is compromised, the attacker can execute arbitrary governance proposals without any delay for users to react or exit.

## Bridge.retryMessage ignores address bans and message suspensions
- Location: `Bridge.sol` : `retryMessage()`
- Mechanism: `processMessage()` checks `addressBanned[_message.to]` and `proofReceipt[msgHash].receivedAt` (set by `suspendMessages`) before invoking a message. However, `retryMessage()` performs neither check — it only verifies `messageStatus[msgHash] == RETRIABLE` and then calls `_invokeMessageCall()` unconditionally. A message that was already processed (and failed, entering `RETRIABLE` state) before an address was banned or a message was suspended can still be executed via `retryMessage()`.
- Impact: A watchdog ban on a malicious contract or a suspension of a specific message can be circumvented for any message already in `RETRIABLE` status, allowing execution of arbitrary calls to the banned/suspended target.

## TimelockTokenPool.withread signature lacks EIP-191 prefix and domain separation
- Location: `TimelockTokenPool.sol` : `withdraw(address _to, bytes memory _sig)`
- Mechanism: The hash signed by the grant recipient is `keccak256(abi.encodePacked("Withdraw unlocked Taiko token to: ", _to))` with no EIP-191 `\x19Ethereum Signed Message` prefix, no chain ID, and no contract address. `ECDSA.recover` is called on the raw hash. The same signature can be replayed across every deployment of `TimelockTokenPool` (the codebase explicitly states multiple instances will be deployed for different roles).
- Impact: A signature authorizing withdrawal to a given address on one `TimelockTokenPool` instance can be replayed to trigger simultaneous withdrawals on all other instances where the same recipient has a grant, potentially withdrawing tokens before the recipient intended.
