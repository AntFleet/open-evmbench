# Audit: 2025-10-sequence

## Estimator Executes Payload Instead of Simulating
- Location: src/Estimator.sol : estimate
- Mechanism: `estimate` decodes the payload, calls `_consumeNonce(decoded.space, readNonce(decoded.space))`, performs `signatureValidation`, then invokes the private `_estimate` helper (which performs the full call loop with LibOptim.call/delegatecall, error-flag handling, behaviorOnError branches, and nonce-consuming side effects) before returning `startingGas - gasleft()`. The `_isValidImage` override unconditionally returns true after the super call, and the function is marked `payable nonReentrant`.
- Impact: Any caller supplying a valid signature can execute an arbitrary payload (state mutations, nonce consumption, value transfers, delegate calls) by invoking the "estimate" entrypoint; the function name and return value give a false impression that only gas measurement occurs.

## Static Signature Allows Unauthorized Execution After Timestamp
- Location: src/modules/auth/BaseAuth.sol : signatureValidation (and getStaticSignature/setStaticSignature)
- Mechanism: When the first byte of `_signature` has bit 0x80 set, `signatureValidation` reads an `(address, uint256 timestamp)` tuple from `STATIC_SIGNATURE_KEY` storage via `_getStaticSignature(opHash)` and accepts the payload if `timestamp > block.timestamp` (with an additional `msg.sender == addr` check only when `addr != address(0)`). The setter is `onlySelf`.
- Impact: An attacker who can cause a static signature entry to be written (via a prior self-call or compromised module) can later execute the corresponding payload from any caller after the recorded timestamp, bypassing the normal image-hash / threshold signature path.

## Chained Signature Checkpointer Snapshot Can Be Bypassed
- Location: src/modules/auth/BaseSig.sol : recoverChained (and recover)
- Mechanism: When the signature flag has bit 0x40 set, the code reads a checkpointer address and optional data, calls `ICheckpointer.snapshotFor`, then proceeds with chained recovery; the snapshot is only enforced if `snapshot.imageHash != imageHash && checkpoint <= snapshot.checkpoint`. The final imageHash is computed from the last chained signature.
- Impact: An attacker supplying a chained signature sequence can choose a checkpointer that returns a stale or attacker-controlled snapshot, allowing reuse of an older configuration imageHash whose checkpoint is still accepted.

## Recovery Queue Does Not Enforce Caller or Payload Integrity
- Location: src/extensions/recovery/Recovery.sol : queuePayload (and isValidSignature)
- Mechanism: `queuePayload` accepts any `_wallet`/`_signer` pair, verifies the signature only against `recoveryPayloadHash(_wallet, _payload)`, then blindly writes `timestampForQueuedPayload[_wallet][_signer][payloadHash] = block.timestamp`. `isValidSignature` performs ECDSA or ERC-1271 checks on the recovery hash but never checks that the caller is `_wallet` or that the payload matches the on-chain context.
- Impact: Any party can queue a recovery payload for an arbitrary wallet/signer pair; later the recovery leaf can be used on that wallet even though the queuing transaction was never authorized by the wallet itself.

## SessionManager Allows Self-Call to Bypass Usage-Limit Enforcement
- Location: src/extensions/sessions/SessionManager.sol : recoverSapientSignature (via _validateExplicitCall and _validateLimitUsageIncrement)
- Mechanism: The loop over `payload.calls` rejects delegate calls and self-calls except when `call.to == address(this)` and the call is the incrementUsageLimit selector; the first call is then required to be exactly `REVERT_ON_ERROR && !onlyFallback` with data matching the computed limits. No check prevents a later call in the same payload from also targeting `address(this)`.
- Impact: After the mandatory increment call, an attacker can include additional self-calls that mutate session state or call other SessionManager functions, violating the "only the increment call is allowed" invariant.

## Simulator and Estimator Both Lack Nonce/Signature Isolation
- Location: src/Simulator.sol : simulate and src/Estimator.sol : estimate
- Mechanism: Neither function isolates the simulated/estimated execution from the live nonce and storage; Estimator explicitly consumes the nonce while Simulator executes the call loop (including delegate calls to `handleSequenceDelegateCall`) directly on the live contract state.
- Impact: On-chain simulation or estimation calls can advance nonces or perform state changes that affect subsequent real transactions, enabling griefing or replay protection bypass.
