# Audit: 2025-10-sequence

## Chained signature can bypass checkpointer validation
- Location: `src/modules/auth/BaseSig.sol` : `recover`, `recoverChained`
- Mechanism: `recover` only loads the checkpointer snapshot when the outer signature flag has bit `0x40` set. For chained signatures, if the outer flag enables chaining but leaves `0x40` unset, `_checkpointer` and `snapshot` remain zero-valued before entering `recoverChained`. Inner signatures are then recovered with `_ignoreCheckpointer == true`, so an inner signature can still encode the stale checkpointer address for image-hash reconstruction while skipping the `snapshotFor` call and all snapshot freshness checks. The final `UnusedSnapshot` checks also do nothing because the outer snapshot is zero.
- Impact: A signer from an old wallet configuration can use a chained signature to authorize operations even after a checkpointer has advanced the wallet to a newer configuration that removes them. This can allow unauthorized wallet execution, including fund transfers or configuration changes.

## Session call signatures can be replayed as partial payloads
- Location: `src/extensions/sessions/SessionSig.sol` : `recoverSignature`, `hashCallWithReplayProtection`; `src/modules/Calls.sol` : `execute`, `_execute`
- Mechanism: Session signatures are checked per call over only `chainId`, `space`, `nonce`, `callIdx`, and `Payload.hashCall(payload.calls[callIdx])`. They are not bound to the complete call array or full payload hash. If a multi-call execution reverts, nonce consumption is reverted too, leaving the observed session signatures reusable. An attacker can then build a shorter payload, such as a prefix of the original calls preserving call indices, and reuse the corresponding per-call signatures.
- Impact: Calls intended to execute atomically with later checks or cleanup calls can be executed alone. A mempool attacker can front-run a valid multi-call session with a partial payload, consume the nonce, block the intended transaction, and leave the wallet in a financially harmful partial state.

## Cumulative session limits are not persisted
- Location: `src/extensions/sessions/explicit/PermissionValidator.sol` : `validatePermission`
- Mechanism: For cumulative parameter rules, the code computes the updated cumulative amount in a local `UsageLimit memory usageLimit` and sets `usageLimit.usageAmount = value256`, but never writes that updated struct back into `newUsageLimits[j]`. The returned usage-limit array therefore contains zero or stale amounts, and `_validateLimitUsageIncrement` requires an `incrementUsageLimit` call using those stale values.
- Impact: Explicit session keys can repeatedly use permissions protected by cumulative limits without advancing stored usage. Spend or call caps enforced through cumulative rules can be bypassed across payloads, and even across multiple calls in the same payload.

