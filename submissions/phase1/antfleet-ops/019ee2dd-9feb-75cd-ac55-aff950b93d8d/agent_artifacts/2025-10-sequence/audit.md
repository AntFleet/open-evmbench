# Audit: 2025-10-sequence

 ## ERC-4337 execution path is permanently reverted due to reentrancy-guard conflict
- Location: `src/modules/ERC4337v07.sol` : `executeUserOp`
- Mechanism: `executeUserOp` carries the `nonReentrant` modifier and then calls `this.selfExecute(_payload)` externally. `selfExecute` also carries `nonReentrant`. The outer call writes the shared reentrancy status slot to `_ENTERED`; the inner call's `nonReentrant` check reads the same slot, sees `_ENTERED`, and reverts with `ReentrantCall` before any payload runs.
- Impact: Every ERC-4337 user operation routed through `executeUserOp` reverts unconditionally, so the wallet cannot execute user operations via the EntryPoint.

## Estimator bypasses image-hash validation and executes arbitrary calls
- Location: `src/Estimator.sol` : `_isValidImage`, `estimate`, and inherited `execute` from `Calls`
- Mechanism: `Estimator._isValidImage` calls `super._isValidImage(_imageHash)` but discards the result and returns `true`, so `signatureValidation` accepts any image hash. `estimate` then consumes the current nonce via `_consumeNonce(decoded.space, readNonce(decoded.space))`, validates a signature against the arbitrary image hash, and runs `_estimate`, which executes arbitrary external calls and `delegatecall`s. The inherited `execute` is exposed with the same bypass.
- Impact: Anyone can call `estimate`/`execute` on the Estimator with a self-generated signature, advance its nonce, and perform state-changing or delegate calls from the Estimator address, including `selfdestruct`, destroying the helper or draining any ETH it holds.

## Simulator allows unauthenticated arbitrary delegate calls
- Location: `src/Simulator.sol` : `simulate`
- Mechanism: `simulate` is external, requires no signature or nonce, and executes a caller-supplied array of calls. When `call.delegateCall` is true it performs `LibOptim.delegatecall(call.to, ..., <caller-controlled data>)`, running the target code in the Simulator's own storage context.
- Impact: Any caller can destroy the Simulator (e.g., delegatecall to a contract that invokes `selfdestruct`) or overwrite its storage slots because there is no access control.

## Calls to non-contract addresses succeed silently
- Location: `src/utils/LibOptim.sol` : `call` / `delegatecall`; consumers: `src/modules/Calls.sol:_execute`, `src/Estimator.sol:_estimate`, `src/Simulator.sol:simulate`, `src/Guest.sol:_dispatchGuest`
- Mechanism: `LibOptim.call` and `LibOptim.delegatecall` do not check `extcodesize` and return `true` when the target address has no code. The execution loops treat `success == true` as a successful execution and emit `CallSucceeded`/continue processing.
- Impact: Calls to EOAs, destroyed contracts, or wrong addresses are reported as successful even though no code ran, bypassing `onlyFallback` and error-handling logic and potentially causing loss when later operations depend on the supposed execution.

## Invalid `behaviorOnError` value bypasses failure handling
- Location: `src/modules/Payload.sol` : `fromPackedCalls`; handlers in `src/modules/Calls.sol:_execute`, `src/Estimator.sol:_estimate`, `src/Simulator.sol:simulate`, `src/Guest.sol:_dispatchGuest`
- Mechanism: `fromPackedCalls` stores the top two bits as `behaviorOnError` without validating that the value is one of `BEHAVIOR_IGNORE_ERROR` (0), `BEHAVIOR_REVERT_ON_ERROR` (1), or `BEHAVIOR_ABORT_ON_ERROR` (2). When a call with value `3` fails, none of the `if` branches match, so execution falls through to `emit CallSucceeded`/`Status.Succeeded` and `errorFlag` is never set.
- Impact: A failed call can be misreported as successful, and a subsequent `onlyFallback` call that should execute after an error is skipped, breaking intended call-sequence semantics.

## Hooks fallback silently succeeds for unsupported selectors
- Location: `src/modules/Hooks.sol` : `fallback`
- Mechanism: The fallback reads `msg.sig` and delegatecalls a registered hook; if no hook exists, the function simply returns without reverting.
- Impact: Any call to an unimplemented function selector on the wallet succeeds as a no-op, misleading users and integrations (e.g., a token transfer with a wrong selector appears successful without moving funds) and enabling phishing.

## Signature validation reverts instead of returning invalid for ERC-1271/ERC-4337
- Location: `src/modules/auth/BaseAuth.sol` : `signatureValidation`, `isValidSignature`, `recoverSapientSignature`
- Mechanism: `signatureValidation` reverts on `InvalidSignatureWeight`, `InvalidStaticSignatureExpired`, `InvalidStaticSignatureWrongCaller`, and `InvalidSapientSignature`. `isValidSignature` and `recoverSapientSignature` do not catch these reverts, so they propagate instead of returning the ERC-1271 failure magic value `0x00000000` or a sapient failure result.
- Impact: ERC-1271 consumers and ERC-4337 bundlers expecting a failure flag/magic value receive reverts, breaking composability and potentially causing whole bundles to revert instead of gracefully failing one user operation.

## Static-signature caller restriction breaks ERC-4337 validation
- Location: `src/modules/auth/BaseAuth.sol` : `signatureValidation` static branch; `src/modules/ERC4337v07.sol` : `validateUserOp`
- Mechanism: The static-signature path requires `addr == address(0) || addr == msg.sender`. `validateUserOp` invokes the check via `this.isValidSignature(...)`, an external call that sets `msg.sender` to the wallet contract itself.
- Impact: Static signatures that restrict execution to a specific EOA (`addr != 0`) always revert with `InvalidStaticSignatureWrongCaller` during ERC-4337 validation, making that access-control feature unusable through the EntryPoint.

## Explicit session parameter rules can be bypassed with short calldata
- Location: `src/extensions/sessions/explicit/PermissionValidator.sol` : `validatePermission`; `src/utils/LibBytes.sol` : `readBytes32`
- Mechanism: `validatePermission` reads the value to check from `call.data` at `rule.offset` using `LibBytes.readBytes32`, which performs no bounds check. The EVM returns `0` for reads past the end of `calldata`, so a `NOT_EQUAL` rule that forbids a non-zero value can be satisfied by providing calldata shorter than `rule.offset`.
- Impact: A session signer can submit a call whose guarded parameter is omitted, causing the permission check to see the default value `0` and pass even though the wallet owner intended to forbid that value, potentially allowing an unauthorized call.
