# Audit: 2024-05-arbitrum-foundation

# Open EVMBench Detect Audit Report — Arbitrum Foundation (2024-05)

## Reentrancy in staking pool deposits drains existing funds
- Location: `src/assertionStakingPool/AbsBoldStakingPool.sol` : `depositIntoPool`
- Mechanism: `depositIntoPool` credits `depositBalance[msg.sender]` before `safeTransferFrom` completes. A malicious or non-standard `stakeToken` with transfer hooks can reenter `withdrawFromPool` during `transferFrom`, withdrawing against the newly credited balance while the transfer is still in flight. Those tokens are taken from the pool’s existing balance (other depositors’ funds), not from the attacker’s transfer.
- Impact: An attacker can steal stake already deposited by honest users in `AssertionStakingPool` and `EdgeStakingPool` contracts.

## Staking pool internal balances are not reduced when stake is deployed
- Location: `src/assertionStakingPool/AbsBoldStakingPool.sol` : `withdrawFromPool` (also affects `AssertionStakingPool.createAssertion`, `EdgeStakingPool.createEdge`)
- Mechanism: When stake is moved to the rollup or `EdgeChallengeManager`, `depositBalance` is never decremented. After `createAssertion` / `createEdge`, the contract’s token balance drops by the required stake, but each depositor’s `depositBalance` still reflects their full deposit. If total deposits exceed the required stake, depositors can withdraw against the full mapping while only the excess-over-required amount remains in the contract.
- Impact: Depositors race to withdraw; early withdrawers can take more than their fair share of returned stake, and late withdrawers may be unable to recover funds (loss/theft between pool participants).

## Delay buffer proof validates only the first newly read delayed message
- Location: `src/bridge/SequencerInbox.sol` : `delayProofImpl`
- Mechanism: When a batch advances `afterDelayedMessagesRead` past `totalDelayedMessagesRead` by more than one, `delayProofImpl` validates only the delayed message at index `totalDelayedMessagesRead` and calls `buffer.update` using only that message’s `blockNumber`. Later messages in the same batch are included without delay-buffer validation or per-message buffer accounting.
- Impact: A batch poster can bundle one low-delay message (passing the single proof) with additional long-delayed messages in the same batch, under-depleting the delay buffer and weakening the delay-buffer safety mechanism.

## `sequencerReportedSubMessageCount` continuity check can be bypassed
- Location: `src/bridge/AbsBridge.sol` : `enqueueSequencerMessage`
- Mechanism: The consistency check between stored `sequencerReportedSubMessageCount` and caller-supplied `prevMessageCount` is skipped whenever `prevMessageCount == 0`. A batch poster can pass `prevMessageCount = 0` even after the counter is non-zero, avoid the revert, and overwrite `sequencerReportedSubMessageCount` with an arbitrary `newMessageCount`.
- Impact: A malicious or compromised batch poster can corrupt the L1 sub-message counter used by the protocol, breaking accounting/validation that depends on that counter and potentially affecting L2 batch processing assumptions.

## `getPrevAssertionHash` follows the wrong lower-level edge
- Location: `src/challengeV2/libraries/EdgeChallengeManagerLib.sol` : `getPrevAssertionHash`
- Mechanism: When walking from a higher-level edge toward the assertion chain, the function uses `store.firstRivals[edge.originId]` to pick the lower-level edge. `firstRivals[mutualId]` stores the second rival created in a group, not necessarily the edge referenced by the current edge’s `claimId`. Rival edges at the same level can claim different lower-level histories and have different `originId` values once traversed further.
- Impact: `confirmEdgeByOneStepProof` can validate `prevConfig` against the wrong predecessor assertion hash, potentially accepting a one-step proof under incorrect execution context (invalid challenge outcome) or causing incorrect machine-step derivation.

## Division by zero when `block.basefee` is zero in gas refund path
- Location: `src/libraries/GasRefundEnabled.sol` : `refundsGas` modifier
- Mechanism: When refunding blob gas costs, the modifier computes `(dataHashes.length * gasPerBlob * blobBasefee) / block.basefee` without guarding against `block.basefee == 0`.
- Impact: On chains or blocks with zero base fee, blob batch submission through `addSequencerL2BatchFromBlobs` (and related `refundsGas` entrypoints) reverts, causing a denial of service for batch posting.

## Division by zero in batch spending report on zero base fee
- Location: `src/bridge/SequencerInbox.sol` : `submitBatchSpendingReport`
- Mechanism: On Arbitrum host chains, the function adds `l1Fees / block.basefee` to `extraGas` without checking that `block.basefee > 0`.
- Impact: If `block.basefee` is zero, batch spending report submission reverts, blocking batch-poster reimbursement and potentially preventing batch delivery paths that rely on this internal call.

## Unchecked ERC20 allowance accumulation on rollup/challenge manager
- Location: `src/assertionStakingPool/AssertionStakingPool.sol` : `createAssertion`; `src/assertionStakingPool/EdgeStakingPool.sol` : `createEdge`
- Mechanism: Both functions call `safeIncreaseAllowance` on every invocation without resetting prior allowance. Repeated calls (or failed partial flows in surrounding tooling) monotonically increase approval granted to the rollup or `EdgeChallengeManager`.
- Impact: If the spender contract is compromised or buggy, excess allowance lets it pull more tokens from the pool than intended, beyond the single stake amount required for the current operation.

## `confirmEdgeByTime` can be called without an updated ancestor timer cache
- Location: `src/challengeV2/EdgeChallengeManager.sol` : `confirmEdgeByTime`; `src/challengeV2/libraries/EdgeChallengeManagerLib.sol` : `timeUnrivaledTotal`
- Mechanism: Confirmation uses `timeUnrivaledTotal`, which for bisected edges depends on children’s `totalTimeUnrivaledCache`. Cache updates are optional, separate public calls (`updateTimerCacheByChildren`, `updateTimerCacheByClaim`). If caches are stale/zero, `timeUnrivaledTotal` is understated even when real unrivaled time is sufficient.
- Impact: Honest challengers can be temporarily blocked from time-based confirmation (griefing/DoS) until cache-update transactions are run; conversely, operational mistakes about cache updates can delay assertion resolution beyond the intended challenge timeline.

