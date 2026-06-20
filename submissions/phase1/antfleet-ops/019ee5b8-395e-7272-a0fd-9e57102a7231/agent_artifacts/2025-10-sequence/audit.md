# Audit: 2025-10-sequence

## Chained signatures can bypass checkpointer validation
- Location: `src/modules/auth/BaseSig.sol` : `recover` / `recoverChained`
- Mechanism: The outer chained-signature flag can omit the checkpointer bit (`0x40`), so `recover` enters `recoverChained` with `_checkpointer == address(0)` and an empty `Snapshot`. Inner signatures can still include a checkpointer address, but they are recovered with `_ignoreCheckpointer == true`, so `snapshotFor` is never called and the stale-checkpoint guard is skipped.
- Impact: A signer removed by a newer checkpointer snapshot can keep using an old configuration image hash to authorize wallet operations.

## Session batches can be truncated and replayed
- Location: `src/extensions/sessions/SessionSig.sol` : `hashCallWithReplayProtection`; `src/modules/Calls.sol` : `execute` / `_execute`
- Mechanism: Session signers sign each call independently over `(chainId, space, nonce, callIdx, hashCall)`, not over the full batch hash or call count. If a full session batch reverts, nonce consumption is reverted too; or an attacker can front-run before the full batch lands. The attacker can submit a shorter prefix using the same per-call signatures because the remaining calls were never part of each individual signature.
- Impact: Calls intended to be atomic with later checks, cleanup, or reversal steps can be executed alone, causing partial state changes, lost funds, or griefing while consuming the wallet nonce.

## Cumulative session limits are not persisted
- Location: `src/extensions/sessions/explicit/PermissionValidator.sol` : `validatePermission`
- Mechanism: For cumulative rules, the code computes `value256 += previousUsage` and assigns it to the local `usageLimit.usageAmount`, but the updated amount is not reliably written back into `newUsageLimits`. The increment call later persists stale or zero usage.
- Impact: A session key constrained by cumulative parameter limits can repeatedly spend or call up to the per-call limit without the lifetime/session usage increasing correctly.

## Session signatures replay across wallets
- Location: `src/extensions/sessions/SessionSig.sol` : `hashCallWithReplayProtection`
- Mechanism: The per-call session hash omits the wallet address. Two wallets with the same session configuration and matching nonce space/nonce will accept the same session call signatures.
- Impact: A signature intended for one wallet can be replayed against another compatible wallet, executing the same call from that second wallet without wallet-specific authorization.

## Estimator authorizes arbitrary configurations
- Location: `src/Estimator.sol` : `_isValidImage` / `estimate`
- Mechanism: `_isValidImage` discards `super._isValidImage(_imageHash)` and always returns `true`. `estimate` also consumes `readNonce(space)` instead of the signed nonce, then performs real calls/delegatecalls.
- Impact: If deployed or used as an implementation, any attacker can self-authorize with an attacker-chosen config and execute arbitrary actions from the Estimator/wallet context.

## Simulator performs real unauthenticated execution
- Location: `src/Simulator.sol` : `simulate`
- Mechanism: `simulate` is external and performs arbitrary `call` and `delegatecall` operations without signature validation, access control, or reverting state at the end.
- Impact: Any caller can spend assets/allowances held by the Simulator or mutate its storage through delegatecall.

