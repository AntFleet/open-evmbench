# Audit: 2025-10-sequence

## Cumulative session limits are never persisted
- Location: `src/extensions/sessions/explicit/PermissionValidator.sol` : `validatePermission`
- Mechanism: For cumulative rules, the function computes a new `usageAmount` in the local `usageLimit` variable, but never writes that updated struct back into `newUsageLimits`. As a result, the array returned to `SessionManager` still contains zero or stale amounts. The later `_validateLimitUsageIncrement` step therefore approves a first-call `incrementUsageLimit(...)` payload built from incorrect counters, and `incrementUsageLimit` accepts those no-op/stale values as long as they do not decrease storage. The same bug also means multiple calls in one payload do not accumulate against each other, because later calls fall back to storage instead of the in-memory increment.
- Impact: Any explicit session key protected by cumulative parameter limits can exceed its intended lifetime cap. An attacker can split usage across multiple calls or transactions and keep the tracked usage effectively at zero, bypassing spend/amount/rate limits that are supposed to accumulate over time.

## Session signatures can be replayed across different wallets
- Location: `src/extensions/sessions/SessionSig.sol` : `hashCallWithReplayProtection`
- Mechanism: The session signer signs only `chainId`/`space`/`nonce`/`callIdx`/`callHash`. The wallet address is never included in the signed digest. `SessionManager.recoverSapientSignature` uses `msg.sender` only for permission lookup and usage accounting after signature recovery, so the same encoded session signature remains valid on any wallet that has the same `SessionManager` leaf configuration and matching nonce space/nonce.
- Impact: If two wallets share the same session configuration, a signature collected for wallet A can be replayed on wallet B. That lets a party with one valid session signature execute the same authorized calls from other wallets that reused that session image.

## `Estimator` accepts forged signatures and executes arbitrary calls
- Location: `src/Estimator.sol` : `_isValidImage`
- Mechanism: The override calls `super._isValidImage(_imageHash)` but discards the result and always returns `true`. In `estimate`, that breaks the final authorization check performed by `BaseAuth.signatureValidation`. Because `BaseSig.recover` allows a zero-threshold/zero-weight signature encoding, an attacker can submit a trivial forged signature and still pass validation. `estimate` then runs `_estimate`, which performs attacker-controlled `call` and `delegatecall` operations.
- Impact: Any caller can make the `Estimator` contract execute arbitrary external calls or delegatecalls, draining any ETH/tokens it holds, corrupting its storage, or abusing any privileges/allowances granted to the estimator address.

## `Simulator` performs real state-changing execution without authorization
- Location: `src/Simulator.sol` : `simulate`
- Mechanism: Despite being presented as a simulation helper, `simulate` is an unrestricted external function that directly performs `LibOptim.call` and `LibOptim.delegatecall` over attacker-supplied calls. It is not `view`, does not authenticate the caller, and does not wrap execution in a revert/rollback mechanism, so all side effects persist.
- Impact: Any caller can use the `Simulator` contract as an arbitrary execution primitive. If it ever holds assets, approvals, or trusted privileges, an attacker can spend them; otherwise they can still mutate the simulator’s own storage via delegatecall and trigger real side effects on external contracts.

