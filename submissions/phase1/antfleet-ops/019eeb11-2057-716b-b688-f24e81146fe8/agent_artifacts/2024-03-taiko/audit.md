# Audit: 2024-03-taiko
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

I merged all 6 reports (claude-opus-4-8 ×3, gpt-5.5 ×3; M = 6). I identified **11 distinct findings** across the inputs and all 11 appear below — no drops.

## Consensus findings

## SGX prover registration does not pin the enclave identity (MRENCLAVE/MRSIGNER)
*(consensus, 5 of 6 reports)*
- Location: `packages/protocol/contracts/automata-attestation/AutomataDcapV3Attestation.sol` : `_verifyParsedQuote` (the `if (_checkLocalEnclaveReport)` Step‑2 block) — reached via `packages/protocol/contracts/verifiers/SgxVerifier.sol` : `registerInstance` / `_addInstances`
- Mechanism: `_checkLocalEnclaveReport` is a storage bool that defaults to `false` (only flipped by owner‑only `toggleLocalReportCheck()`). While false, `_verifyParsedQuote` validates a genuine Intel‑signed quote (QE identity, PCK chain to the Intel root, TCB status, ECDSA signature) but never checks the application enclave's `mrEnclave`/`mrSigner` against `_trustedUserMrEnclave`/`_trustedUserMrSigner`. The quote thus proves "some genuine SGX CPU," not "the Taiko prover binary." `registerInstance` then registers `address(bytes20(localEnclaveReport.reportData))` — an enclave‑chosen value — as a trusted instance.
- Impact: Under the default config, anyone with any SGX‑capable machine can run arbitrary enclave code, embed an attacker‑controlled address in `reportData`, obtain a passing attestation, and register a trusted SGX instance. After `INSTANCE_VALIDITY_DELAY` (~1 day) that key signs arbitrary `Transition`s that `SgxVerifier.verifyProof` accepts, enabling fraudulent finalization of invalid L2 state and theft of bridged funds. Insecure‑by‑default: safety depends on an out‑of‑band owner action with no on‑chain enforcement.
- Reviewer disagreement: None — opus‑3 separately validated the SGX cert‑chain **revocation** path (`_verifyCertChain`) as sound, but did not address this enclave‑identity gap.

## Timelock admin can bypass the governance minimum delay
*(consensus, 3 of 6 reports)*
- Location: `packages/protocol/contracts/L1/gov/TaikoTimelockController.sol` : `getMinDelay`
- Mechanism: `getMinDelay()` returns `hasRole(TIMELOCK_ADMIN_ROLE, msg.sender) ? 0 : super.getMinDelay()`. OZ `schedule()` enforces `delay >= getMinDelay()` and `execute()` only requires the op be ready; `init()` grants the deploy `owner()` the `TIMELOCK_ADMIN_ROLE`. An admin can therefore `schedule()` with `delay == 0` and `execute()` in the same block.
- Impact: The timelock provides no time‑delay guarantee against the admin role; a malicious/compromised admin pushes privileged upgrades or parameter changes through with zero notice, removing the community‑reaction window. Documented as intentional, but it nullifies the timelock's protective purpose — a single‑point‑of‑failure trust assumption.
- Reviewer disagreement: None; finders note it is code‑commented as intentional.

## AssignmentHook charges ERC20 prover fees to an arbitrary approved account (caller‑controlled coinbase)
*(consensus, 3 of 6 reports)*
- Location: `packages/protocol/contracts/L1/hooks/AssignmentHook.sol` : `onBlockProposed` / `hashAssignment`; `packages/protocol/contracts/L1/libs/LibProposing.sol` : `proposeBlock`
- Mechanism: Proposer‑supplied `params.coinbase` is copied into `_meta.coinbase`. For ERC20 prover fees, `onBlockProposed` does `safeTransferFrom(_meta.coinbase, _blk.assignedProver, proverFee)`, but the signed assignment hash does not bind the payer/proposer/coinbase and the hook never requires `_meta.coinbase == msg.sender`.
- Impact: A malicious assigned prover/proposer signs their own assignment, sets `coinbase` to any victim holding an outstanding `feeToken` allowance to the hook, and drains that allowance to the prover. Preconditions: a valid prover assignment + an existing victim allowance to `AssignmentHook`.
- Reviewer disagreement: None directly; opus‑3 reviewed hook execution for nested‑hook TKO draining (post‑hook balance‑equality check) but did not address the coinbase‑as‑payer authorization gap.

## `txListByteSize` silently truncated to uint24 while the committed hash covers the full list
*(consensus, 2 of 6 reports)*
- Location: `packages/protocol/contracts/L1/libs/LibProposing.sol` : `proposeBlock` (calldata‑DA branch — `meta_.txListByteSize = uint24(_txList.length);` before the `> blockMaxTxListBytes` check)
- Mechanism: `_txList.length` (uint256) is downcast to uint24 before the size‑bound check and before inclusion in `metaHash`. For length `2**24 + k`, the stored size wraps to `k`, passing the bound check, while `meta_.blobHash = keccak256(_txList)` commits to the full payload — so on‑chain size metadata disagrees with the data the hash binds, and nodes slice the txList by the truncated value.
- Impact: Desynchronizes on‑chain metadata from committed DA data. Both finders flag it as the downcast‑truncation class to harden (bound `_txList.length` before the cast) but explicitly state it is **not** practically exploitable: blob DA is disabled so calldata is mandatory, and >16 MB of calldata costs far more gas than any configured block limit.
- Reviewer disagreement: opus‑2 reviewed truncating downcasts generally and reported no truncation bug in the paths it examined (focused on bond `uint96`/`uint64` casts).

## Bridge watchdog can forge proven message receipts
*(consensus, 2 of 6 reports)*
- Location: `packages/protocol/contracts/bridge/Bridge.sol` : `suspendMessages` / `processMessage` / `recallMessage`
- Mechanism: `suspendMessages(..., false)` writes `proofReceipt[msgHash].receivedAt = uint64(block.timestamp)` for any caller‑supplied hash, without requiring an existing sent/proven/suspended receipt. `processMessage` and `recallMessage` treat any nonzero `receivedAt` as already‑proven and skip `_proveSignalReceived`; `recallMessage` also skips the "message was ever sent" check.
- Impact: A compromised/malicious `bridge_watchdog` can pre‑seed arbitrary fabricated hashes, wait the invocation delay, then process or recall them with no source‑chain proof — minting bridged vault assets, releasing escrowed assets, recalling source‑chain ETH, or invoking arbitrary bridge targets, subject to liquidity.
- Reviewer disagreement: opus‑1 and opus‑2 reviewed `Bridge.processMessage`/`recallMessage` value‑refund and invocation‑delay logic and called it internally consistent, but neither addressed the watchdog `suspendMessages` receipt‑forging vector.

## SGX instances can self‑renew / rotate keys without fresh attestation
*(consensus, 2 of 6 reports)*
- Location: `packages/protocol/contracts/verifiers/SgxVerifier.sol` : `verifyProof` / `_replaceInstance`
- Mechanism: `verifyProof` accepts a `newInstance` taken from proof data signed by the current instance; `_replaceInstance` writes `instances[id] = Instance(newInstance, block.timestamp)` without requiring `newInstance != oldInstance`, `newInstance != address(0)`, or a fresh Intel quote. The old key alone picks the next key and resets `validSince`.
- Impact: Control of one valid SGX key is enough to bypass `INSTANCE_EXPIRY` indefinitely by rotating before expiry (even to itself), or to hand validity to an attacker‑controlled un‑attested key — defeating the intended key‑expiry / side‑channel mitigation model.
- Reviewer disagreement: None; no other report addressed `_replaceInstance` rotation.

## Guardian approvals do not bind the proof data that controls liveness‑bond return
*(consensus, 2 of 6 reports)*
- Location: `packages/protocol/contracts/L1/provers/GuardianProver.sol` : `approve`; `packages/protocol/contracts/L1/libs/LibProving.sol` : `proveBlock`
- Mechanism: Guardian approvals are accumulated over `keccak256(abi.encode(_meta, _tran))` only; `_proof.data` is excluded. Once quorum is reached, the final submitting guardian supplies `_proof.data`, and `proveBlock` treats the sentinel `RETURN_LIVENESS_BOND` as an instruction to refund the assigned prover's liveness bond (`GuardianVerifier` only checks caller == `guardian_prover`).
- Impact: A single final guardian can unilaterally attach the liveness‑bond‑return side effect after others approved only the transition; a colluding final guardian + assigned prover can avoid the intended liveness‑bond forfeiture without threshold approval of that economic outcome.
- Reviewer disagreement: None; no other report addressed the GuardianProver approval/proof‑data binding.

## Minority findings

## Top‑tier (guardian) re‑prove path is permanently bricked by a stale `assert`
*(minority, 1 of 6 reports)*
- Location: `packages/protocol/contracts/L1/libs/LibProving.sol` : `proveBlock` (top‑tier `else { … if (isTopTier) assert(ts.validityBond == 0 && ts.contestBond == 0 && ts.contester == address(0)); }` branch), interacting with `_overrideWithHigherProof` (sets `_ts.contestBond = 1;`)
- Mechanism: The first guardian proof goes through `_overrideWithHigherProof` (since `_proof.tier (1000) > ts.tier (0)`), which writes `ts.contestBond = 1` as a gas‑saving placeholder ("doesn't have any significance"). A second guardian transition for the same block has `_proof.tier == ts.tier == TIER_GUARDIAN`, enters the `else` branch, and hits the top‑tier re‑prove assert, where `contestBond == 0` now evaluates `1 == 0` and reverts with a Panic.
- Impact: The path explicitly meant to let the highest tier re‑prove with a corrected `blockHash`/`stateRoot` ("The top tier prover re‑proves.") always reverts, so the *first* guardian transition is irreversible. If guardians ever approve an incorrect transition (operational error or sub‑threshold compromise landing the first proof), honest guardians cannot supersede it and the wrong transition finalizes after cooldown — removing the guardian tier's self‑correction, the reason a top tier exists.
- Reviewer disagreement: opus‑2 and opus‑3 independently reviewed `LibProving.proveBlock` / `_overrideWithHigherProof` bond flows and reported no exploitable issue, but neither flagged this assert vs `contestBond == 1` contradiction.

## TimelockTokenPool undercharges fractional token grants
*(minority, 1 of 6 reports)* *(conflicting reviews: 1 of 6 reports defended this code path)*
- Location: `packages/protocol/contracts/team/TimelockTokenPool.sol` : `getMyGrantSummary` / `_withdraw`
- Mechanism: `amountToWithdraw` is computed at wei precision, but `costToWithdraw` first truncates `amountUnlocked / 1e18` and charges only whole tokens. Fractional unlocked TKO is withdrawable while its purchase cost rounds down to zero.
- Impact: A grantee with `costPerToken > 0` can withdraw fractional TKO without paying its cost. Sub‑one‑token grants, fractional remainders, or timed withdrawals before whole‑token boundaries let recipients underpay the shared vault.
- Reviewer disagreement: opus‑1 listed "vesting math in `TimelockTokenPool`" among the accounting it reviewed and called "internally consistent."

## High‑tier proof‑tier sampling is grindable
*(minority, 1 of 6 reports)*
- Location: `packages/protocol/contracts/L1/libs/LibProposing.sol` : `proposeBlock`; `packages/protocol/contracts/L1/tiers/MainnetTierProvider.sol` : `getMinTier`
- Mechanism: The required tier is derived from `keccak256(block.prevrandao, b.numBlocks, block.number)` then sampled `_rand % 1000`. A proposer can observe the outcome and abandon/fail proposals that land on the expensive sampled tier, retrying only low‑tier blocks.
- Impact: Probabilistic SGX+ZKVM sampling can be evaded by an attacker who can forge/compromise the lower tier and tolerate failed attempts or forfeited bonds on sampled blocks, defeating the higher‑tier deterrent.
- Reviewer disagreement: None; no other report addressed the tier‑sampling randomness.

## TimelockTokenPool withdrawal signatures are replayable across time and pools
*(minority, 1 of 6 reports)*
- Location: `packages/protocol/contracts/team/TimelockTokenPool.sol` : `withdraw(address,bytes)`
- Mechanism: The signed message is only `keccak256("Withdraw unlocked Taiko token to: ", _to)` — no nonce, deadline, amount, chainId, contract address, or grant id — and `_withdraw` always transfers the currently withdrawable amount.
- Impact: Anyone holding one valid signature can reuse it indefinitely to sweep future unlocks to the same `_to`, and can replay it against other `TimelockTokenPool` deployments where the signer has grants. Preconditions: one valid recipient signature + later/cross‑pool balances.
- Reviewer disagreement: None directly addressed the signature scheme; opus‑1's "vesting math is consistent" note concerned unlock accounting, not signature replay/authentication.

---

*Reconciliation: 11 distinct input findings (by code path + root cause) → 11 output findings (7 consensus + 4 minority). No finding dropped; no two findings merged across differing code paths or root causes (e.g., the guardian `assert`‑brick and the guardian proof‑data‑binding issue both touch `LibProving.proveBlock`/GuardianProver but have distinct root causes and are kept separate).*

