# Audit: 2025-10-sequence

I performed a full pass over the wallet core (auth/signature recovery, nonce, calls, hooks), the ERC‑4337 path, and the extensions (passkeys, recovery, and the explicit/implicit session managers). Below is what I found.

## Summary

This is the Sequence v3 modular smart‑wallet. The security‑critical machinery is internally consistent, and the parts that look alarming on first read are actually safe by construction. I did **not** find a clear, exploitable vulnerability in the trust path. The most important thing to record is *why* the suspicious‑looking spots are not bugs, plus one genuine (low‑impact) access‑control observation on the simulation helper.

## Genuine observation

### Unauthenticated arbitrary call/delegatecall in the Simulator
- Location: `src/Simulator.sol` : `simulate`
- Mechanism: `simulate` is `external` with no signature check, no `onlySelf`, and no nonce. It iterates the caller‑supplied `_calls` and performs `LibOptim.call` / `LibOptim.delegatecall` to arbitrary `call.to`. The `delegatecall` executes attacker‑chosen code in the Simulator's own storage context (it is not a proxy delegating to a fixed implementation).
- Impact: Anyone can make the Simulator execute arbitrary external calls as `msg.sender == Simulator`, or run arbitrary code in its context (including `selfdestruct`/storage corruption pre‑Cancun griefing). This is **only** a real problem if the deployed Simulator is ever funded or granted token approvals/permissions by another contract — which it should never be. It is intentionally an off‑chain (`eth_call` + state‑override) helper. Flagging it as informational; do not deploy it as a live wallet implementation or give it allowances.

## Items I specifically checked and ruled out (so they are not mistaken for bugs)

- **`Estimator._isValidImage` always returns `true`** (`src/Estimator.sol`) and **`Estimator.estimate` consumes `readNonce(space)` instead of the signed nonce** — intentional for gas estimation under state‑override; the Estimator is not a funded/live wallet implementation, so the resulting "signature replay" is not reachable in production.
- **Forged threshold/checkpoint in `BaseSig.recover`** — `threshold`, `checkpoint`, and `checkpointer` are folded into `imageHash` (`fkeccak256(imageHash, threshold)` …) before `_isValidImage`, so lowering the threshold in the signature changes the imageHash and fails validation. Weight cannot be inflated via `ecrecover` returning `address(0)` because the resulting `address(0)` leaf won't match any real config.
- **Static‑signature path** (`BaseAuth.signatureValidation`) — only callable after `setStaticSignature` (onlySelf); unset hashes have `timestamp == 0` and revert as expired.
- **Recovery domain vs. queue key mismatch** (`src/extensions/recovery/Recovery.sol`) — the signer authorizes over the recovery‑mode domain (`recoveryPayloadHash`), but the queue is keyed by `Payload.hashFor(_payload, _wallet)`, which equals the wallet's execution `opHash`. The mismatch is deliberate and the keys line up at execution time; per‑wallet binding (and optional chain binding) is intact, so no cross‑wallet replay.
- **Session value/usage limits** (`SessionManager` / `ExplicitSessionManager` / `PermissionValidator`) — all `call.value` is summed in `_validateExplicitCall`, implicit calls force `value == 0`, `ABORT_ON_ERROR` is banned, and `_validateLimitUsageIncrement` forces the persisting `incrementUsageLimit` call to be call‑0 with `REVERT_ON_ERROR` and byte‑exact expected data. There is no path to spend value/usage that isn't counted and persisted.
- **`incrementUsageLimit`** is `msg.sender`‑scoped, so a third party can only write to its own usage namespace, not a victim wallet's.
- **Blacklist binary search** (`ImplicitSessionManager._isAddressBlacklisted`) relies on sortedness, which `SessionSig.recoverConfiguration` enforces (`InvalidBlacklistUnsorted`) and binds into the imageHash.
- **`executeUserOp` / `selfExecute`** run without re‑checking the signature, but `_payload` is part of `userOp.callData`, hence part of the `userOpHash` validated in `validateUserOp`; `selfExecute` is `onlySelf`.
- **Hooks fallback delegatecall** targets are settable only via `addHook` (`onlySelf`).

If the benchmark expects a planted high‑severity bug, it is not present in an exploitable form in this snapshot as written — the auth, nonce, session‑limit, and recovery invariants all hold. The only access‑control gap is the intentionally permissionless `Simulator`, which is harmless unless misdeployed.

