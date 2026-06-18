# Audit: 2025-10-sequence

I have both reports in full inline, so no codebase access or sub-agents are needed — this is a synthesis task. Here is the merged report.

---

# Merged Security Audit — Sequence v3 Smart Wallet

This report reconciles two independent audits (Reviewer A = Claude, Reviewer B = Codex). Findings both reviewers describe at the same root cause and code path are merged into **Consensus findings**. Findings raised by only one reviewer — including cases where the other reviewer examined the same code and reached a different conclusion — are listed under **Additional findings**, with the disagreement noted so nothing is silently dropped or upgraded.

---

## Consensus findings

## Simulator executes arbitrary calls/delegatecalls without authorization
*(consensus)*
- Location: `src/Simulator.sol` : `simulate`
- Mechanism: `simulate` is externally callable and performs real `call` and `delegatecall` operations from the simulator contract with **no signature validation and no caller restriction**. Despite the name it does not use `staticcall` and does not revert state at the end. This is intentional for off-chain gas estimation/simulation via state overrides; accordingly the contract is **not deployed by `script/Deploy.s.sol`** (only `Factory`, `Stage1Module`, `Guest`, `SessionManager` are).
- Impact: If a `Simulator` is ever deployed as a real account that holds ETH, tokens, approvals, or meaningful storage, any caller can drain or mutate it by supplying arbitrary calls or delegatecalls. Both reviewers agree there is no on-chain exposure as currently deployed, and that it would become critical if ever deployed funded.

## Estimator accepts attacker-chosen wallet images
*(consensus)*
- Location: `src/Estimator.sol` : `_isValidImage`, `estimate`
- Mechanism: `_isValidImage` calls `super._isValidImage(_imageHash)` but **discards the result and always returns `true`**, so signatures over attacker-chosen configurations are accepted. `estimate` additionally consumes the current nonce (`_consumeNonce(space, readNonce(space))`) so the nonce check always passes, then executes the supplied payload from the estimator contract. Like `Simulator`, it is intentionally permissive and **not deployed by `script/Deploy.s.sol`**.
- Impact: If an `Estimator` is ever deployed holding ETH, tokens, approvals, or meaningful storage, an attacker can self-authorize with a fabricated image hash and execute arbitrary calls or delegatecalls from the estimator contract. No on-chain exposure as currently deployed.

---

## Additional findings (single-reviewer)

## Cumulative session usage limit not persisted across payloads
*(Reviewer B only)*
- Location: `src/extensions/sessions/explicit/PermissionValidator.sol` : `validatePermission` (cumulative rule branch)
- Mechanism: For cumulative parameter rules, the function computes `value256 += previousUsage` and assigns it to the local `usageLimit.usageAmount`, but never writes the updated `usageLimit` back into `newUsageLimits`. `_validateLimitUsageIncrement` then expects an increment containing the stale amount (often `0`), and `incrementUsageLimit` persists that stale value instead of the newly consumed cumulative usage.
- Impact: An explicit session with a cumulative limit would enforce the limit only per payload, not across payloads — a session signer could repeatedly spend/call up to the configured limit across separate nonces without stored usage increasing, bypassing lifetime/session caps.
- Note (disagreement): Reviewer A examined this same path and concluded it is **not a bug**, on the basis that the running `SessionUsageLimits.limits` array is threaded call→call (`sessionUsageLimits.limits = limits`, written back to the per-signer slot), so on later calls the entry is found with a non-zero amount and storage is not re-read; per A the `==0` re-read fires only when true cumulative usage is genuinely `0`. The two reviewers disagree on whether the local `usageLimit` is actually persisted; this finding should be resolved by direct re-verification of the write-back of `newUsageLimits` in `validatePermission`.

## Session call signatures lack wallet binding (cross-wallet replay)
*(Reviewer B only)*
- Location: `src/extensions/sessions/SessionSig.sol` : `hashCallWithReplayProtection`
- Mechanism: The session signer's call hash binds chain ID, nonce space, nonce, call index, and the call hash — but **not the wallet address**. Because session-configuration image hashes are also wallet-independent, the same session-signer signature is valid for any wallet that has installed the same session configuration and has the same nonce available.
- Impact: A signed session transaction intended for one wallet can be replayed against another wallet sharing the same session config, provided the replayed nonce/space is valid on the target wallet.
- Note (disagreement): Reviewer A reviewed `hashCallWithReplayProtection` and considered the session-signature path sound, citing the same field set `(chainId, space, nonce, callIdx, hashCall)` as sufficient ("no call the signer didn't sign can execute"); A did not flag the missing wallet address. Resolve by confirming whether any deployment scenario actually shares one session config across multiple wallets.

## Silent "success" on undefined `behaviorOnError` value (== 3)
*(Reviewer A only)*
- Location: `src/modules/Calls.sol` : `_execute` (the `if (!success) { … }` block, ~lines 95–115); identical mirrored logic in `src/Guest.sol` : `_dispatchGuest`, `src/Estimator.sol` : `_estimate`, and `src/Simulator.sol` : `simulate`.
- Mechanism: `Payload.fromPackedCalls` decodes `behaviorOnError = (flags & 0xC0) >> 6`, yielding the full range `0..3`. `_execute` handles only `0` (IGNORE → set `errorFlag`, continue), `1` (REVERT), and `2` (ABORT → break). When a call **fails** with `behaviorOnError == 3`, no branch matches, control falls through, and the loop emits `CallSucceeded(_opHash, i)` while leaving `errorFlag == false`. A reverted call is recorded as succeeded, and any immediately following `onlyFallback` call (which runs only when the preceding call set `errorFlag`) is silently skipped.
- Impact: Low and signer-controlled. `behaviorOnError` is part of the EIP-712–signed payload (`Payload.hashCall` includes `behaviorOnError`), so a third party cannot set it on a victim's behalf — only the wallet's own signer can author `behavior == 3`. Consequences are confined to that signer's own payload: (a) an on-chain `CallSucceeded` event that misreports a reverted call (misleads indexers/relayers and the wallet's success accounting), and (b) a designed `onlyFallback` recovery/safety step intended to fire on failure does not trigger. Recommendation: make the behavior space total (treat the 4th value as REVERT) or reject `behaviorOnError == 3` at decode time.

## Guest is an unauthenticated, fundless multicall dispatcher
*(Reviewer A only)*
- Location: `src/Guest.sol` : `fallback` (`_dispatchGuest`)
- Mechanism: `Guest.fallback` executes arbitrary packed calls with no signature check. By design it bans `delegateCall` and holds no funds or privileges.
- Impact: Anyone who funds or approves the `Guest` contract exposes those assets to arbitrary callers — the standard "shared dispatcher" footgun, not a protocol flaw. No exposure absent user error.

## Intentional cross-chain / cross-wallet replay surfaces
*(Reviewer A only)*
- Location: `src/modules/auth/BaseSig.sol` — `noChainId` (signature flag bit 1) and `FLAG_SIGNATURE_ANY_ADDRESS_SUBDIGEST`
- Mechanism: `noChainId` zeroes `chainId` in the EIP-712 domain; `FLAG_SIGNATURE_ANY_ADDRESS_SUBDIGEST` validates against `payload.hashFor(address(0))` (wallet address removed). Both deliberately make a legitimately signed, exact operation valid across chains/wallets (each still gated by that chain's nonce).
- Impact: These broaden where an authorized op applies; they do not let an attacker forge a new op. Integrators must never set `noChainId` for a chain-specific intent. (Distinct from the session-signature wallet-binding gap above, which is in `SessionSig.sol`.)

## Owner-only configuration footguns
*(Reviewer A only)*
- Location: `src/modules/Implementation.sol` : `updateImplementation`; `src/modules/Hooks.sol` : `addHook`
- Mechanism: `updateImplementation` accepts any address (a bad value bricks the wallet); `addHook` installs a `delegatecall` target. Both are `onlySelf`, reachable only via a valid self-signed call.
- Impact: Not third-party reachable — these are the wallet owner's own risk (self-inflicted brick / malicious delegatecall target requires the owner's own valid signature).

---

### Verified sound by Reviewer A (no corresponding finding in either report — listed for completeness, not as findings)
Reviewer A additionally re-confirmed against source that the following are **not** exploitable: the auth core weight-binding in `BaseSig`/`BaseAuth` (no leaf type adds weight under an attacker-chosen node hash; `imageHash` binds root+threshold+checkpoint+checkpointer); explicit-session value accounting and the mandatory content-bound `incrementUsageLimit` call[0]; the ban on implicit-call value (`ImplicitSessionManager._validateImplicitCall`); `permissionIdx` selection (still gated by `permission.target == call.to` and the signer's `hashCallWithReplayProtection` signature); `ignoreCheckpointer` cursor handling; recovery store-key/lookup-key consistency (`Payload.hashFor(payload, wallet)`); and nonce/reentrancy protections. These are recorded only to document scope; no action implied.

