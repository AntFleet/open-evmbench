# Audit: 2025-10-sequence
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Session signatures replay across wallets
*(consensus, 3 of 6 reports)*
- Location: `src/extensions/sessions/SessionSig.sol` : `hashCallWithReplayProtection` (with `SessionManager.recoverSapientSignature`)
- Mechanism: The per-call session signer digest includes chain id, nonce space, nonce, call index, and `Payload.hashCall`, but omits the wallet address / `msg.sender` and the session configuration root. The session signer never signs the wallet-bound outer payload hash, and `SessionManager` returns the same `imageHash` for any wallet that installed the same session configuration.
- Impact: A session-signed payload captured for wallet A can be replayed against wallet B if B shares the same session config and nonce-space/nonce state. For e.g. ERC20 `transfer`, the token sees `msg.sender == walletB`, so B's assets move without the signer intending to authorize B.
- Reviewer disagreement: Opus shots broadly asserted that signature/sapient flows are wallet-bound (shot 2: nested/sapient flows bind the caller via `parentWallets` in the EIP-712 hash) and found no recovery flaw, but none specifically traced the omission of the wallet address in `hashCallWithReplayProtection`.

## Public Simulator executes arbitrary unauthenticated calls
*(consensus, 3 of 6 reports)*
- Location: `src/Simulator.sol` : `simulate`
- Mechanism: `simulate` is external, unauthenticated, non-view, and performs caller-supplied `call`/`delegatecall` without reverting at the end. It inherits wallet self-authorized functions, so an attacker can include a call to `address(this)` to pass `onlySelf` checks, and delegatecall mutates the Simulator's own storage.
- Impact: Anyone can drain ETH/tokens held by the deployed Simulator, abuse any approvals/roles granted to it, or mutate its implementation/image hash/hooks/static signatures. If a wallet is ever configured to use Simulator as its implementation, this is a full signature bypass for that wallet.
- Reviewer disagreement: Opus shots 1–3 all defended this as an off-chain `eth_call` gas/simulation singleton that holds no funds and is intentionally NOT deployed by `script/Deploy.s.sol`, hence by-design permissive rather than exploitable. *(conflicting reviews: 3 of 6 reports defended this code path)*

## Cumulative session limits are not persisted
*(consensus, 2 of 6 reports)*
- Location: `src/extensions/sessions/explicit/PermissionValidator.sol` : `validatePermission` (cumulative-rule branch)
- Mechanism: For cumulative parameter rules the function computes `value256 += previousUsage` and assigns the result only to the local `usageLimit.usageAmount`; it never writes the updated struct back into `newUsageLimits`. Newly initialized entries stay at `usageAmount: 0`, so `_validateLimitUsageIncrement` verifies/executes an increment against stale values and storage never advances.
- Impact: An explicit session relying on `cumulative` rules can be exceeded indefinitely — a valid session signer (or anyone holding its signed payloads) can repeatedly spend/call up to the per-call cap, bypassing the intended lifetime/session cap.
- Reviewer disagreement: Opus shots 1–3 explicitly asserted the opposite — that cumulative totals already incorporate storage and persist across payloads via the `getLimitUsage`/`incrementUsageLimit` round-trip, so no double-spend exists. *(conflicting reviews: 3 of 6 reports defended this code path)*

## Permission checks can read bytes outside the executed calldata
*(consensus, 2 of 6 reports)*
- Location: `src/extensions/sessions/explicit/PermissionValidator.sol` : `validatePermission`; `src/utils/LibBytes.sol` : `readBytes32`
- Mechanism: Parameter rules extract values with `call.data.readBytes32(rule.offset)`, but `LibBytes.readBytes32` raw-`calldataload`s without checking `rule.offset + 32 <= call.data.length`, ignoring the `bytes calldata` slice length.
- Impact: A session user can satisfy selector/parameter rules using out-of-band ABI-padding or later calldata bytes while sending shorter/different calldata to the permitted target, bypassing explicit session restrictions when the target accepts short/custom calldata, fallback dispatch, or assembly decoding.
- Reviewer disagreement: Opus shot 1 argued the `unchecked` `LibBytes` read paths revert via calldata-slice bounds rather than mis-decoding. *(conflicting reviews: 1 of 6 reports defended this code path)*

## Estimator `_isValidImage` always returns true
*(consensus, 2 of 6 reports)*
- Location: `src/Estimator.sol` : `_isValidImage`, `estimate`
- Mechanism: `_isValidImage` calls `super._isValidImage(_imageHash)` but discards the result and unconditionally returns `true`. `estimate` is external/payable, consumes a nonce, validates against this always-true image check, then executes the supplied calls.
- Impact: Anyone can craft a trivially valid signature image and execute arbitrary calls from the Estimator. If a wallet is ever configured to use Estimator as its implementation, this is a full signature bypass for that wallet.
- Reviewer disagreement: Opus shots 1–3 defended this as an intentional off-chain `eth_call` helper that is not deployed by `script/Deploy.s.sol`; opus shot 3 listed the same mechanism but classed it informational ("not a vulnerability in the deployed system"). *(conflicting reviews: 3 of 6 reports defended this code path)*

## Invalid ECDSA signature accepted as a zero-address signer leaf
*(consensus, 2 of 6 reports)*
- Location: `src/modules/auth/BaseSig.sol` : `recoverBranch`
- Mechanism: The ECDSA branches call `ecrecover` and immediately add the configured weight for the recovered address without rejecting `address(0)`. Malformed ECDSA inputs return `address(0)`, and the code constructs the normal signer leaf for `address(0)` with that weight.
- Impact: If a wallet configuration contains a weighted zero-address signer leaf, anyone can supply an invalid signature and receive that signer's weight; a malformed zero-address signer in a threshold/nested config can make the wallet publicly executable.
- Reviewer disagreement: Opus shots 1–2 explicitly defended this as safe because forgery is prevented by binding the recovered Merkle `root` to the configured `imageHash` (a `0` leaf only counts if the config itself committed to a `0`-address leaf); opus shot 3 made the same general `_isValidImage`-binding argument. *(conflicting reviews: 2 of 6 reports defended this code path)*

## Invalid ECDSA signature accepted when `_signer == address(0)` in Recovery
*(consensus, 2 of 6 reports)*
- Location: `src/extensions/recovery/Recovery.sol` : `isValidSignature` (the 64-byte `ecrecover` block, reachable from permissionless `queuePayload`)
- Mechanism: For a 64-byte signature it computes `addr = ecrecover(rPayloadHash, v, r, s)` and returns `true` when `addr == _signer`. `ecrecover` returns `address(0)` for malformed inputs and `_signer` is a fully caller-controlled argument, so passing `_signer == address(0)` with any non-recoverable blob yields `addr == _signer == address(0)` and is treated as valid.
- Impact: Anyone can queue arbitrary payloads under the `address(0)` recovery slot without a key; if a wallet's committed recovery config ever contains a `FLAG_RECOVERY_LEAF` with `signer == address(0)`, those payloads become consumable, granting recovery authority. (Both finders note it is inert against a sanely configured wallet that never authorizes a zero signer.)
- Reviewer disagreement: None defended this specific path; opus shot 3 raised it itself as a genuine (but practically inert) signature-validation defect.

## Undefined `behaviorOnError == 3` reports a failed call as succeeded and suppresses `onlyFallback`
*(consensus, 2 of 6 reports)*
- Location: `src/modules/Payload.sol` : `fromPackedCalls` (`behaviorOnError = (flags & 0xC0) >> 6`) with `src/modules/Calls.sol` : `_execute` (the `if (!success)` ladder); same pattern in `Guest._dispatchGuest`, `Estimator._estimate`, `Simulator.simulate`
- Mechanism: `behaviorOnError` is a 2-bit field that can be `3`, but only `0/1/2` (`IGNORE`/`REVERT`/`ABORT`) are handled. A call failing with value `3` matches none of the branches, falls through to `emit CallSucceeded`, and never sets `errorFlag`. `SessionManager.recoverSapientSignature` bans only `BEHAVIOR_ABORT_ON_ERROR` (2), not 3, so it is reachable via a session-signed payload.
- Impact: No direct fund/state loss, but event/observability integrity is broken — off-chain relayers/indexers keying off `CallSucceeded`/`CallFailed` are told a reverted call succeeded, and a following `onlyFallback` (compensating) call is silently skipped because `errorFlag` stayed false. Requires an authorized/semi-trusted signer (a session signer counts), so it is a signer footgun, not an unauthenticated-attacker primitive.
- Reviewer disagreement: Opus shot 1 surfaced the identical mechanism but framed it as "a caveat for completeness rather than a finding," judging it harmless in every traced path. *(conflicting reviews: 1 of 6 reports treated this code path as harmless)*

## Minority findings

## Guest can spend stuck ETH
*(minority, 1 of 6 reports)*
- Location: `src/Guest.sol` : `fallback` / `_dispatchGuest`
- Mechanism: `Guest` is a payable, unauthenticated dispatcher that executes arbitrary calls using `call.value` from the contract's own balance. It does not account for `msg.value` versus pre-existing balance; empty/malformed payable calls can leave ETH stuck, and a later call can spend it.
- Impact: Anyone can drain ETH accidentally left in (or force-funded to) the deployed Guest contract. Precondition: Guest holds a positive ETH balance.
- Reviewer disagreement: Opus shot 1 defended Guest as a "privilege-less batch dispatcher holding no funds … benign by design." *(conflicting reviews: 1 of 6 reports defended this code path)*

---

*Reconciliation check: 9 distinct findings identified across the 6 input reports (by code path + root cause); 9 emitted (8 consensus, 1 minority). The two zero-address-`ecrecover` issues are kept separate because they live in different code paths (`BaseSig.recoverBranch` vs `Recovery.isValidSignature`). Opus shots 1 and 2 reported zero genuine findings; all of their substantive claims are preserved above as reviewer-disagreement/defense lines rather than dropped.*

