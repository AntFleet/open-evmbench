# Audit: 2024-05-arbitrum-foundation
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

### Force inclusion ignores the configured timestamp (`delaySeconds`) delay
*(consensus, 5 of 6 reports)*
- Location: `src/bridge/SequencerInbox.sol` : `forceInclusion`
- Mechanism: `forceInclusion` enforces only the block-number portion of the sequencer's exclusive window (`if (l1BlockAndTime[0] + delayBlocks_ >= block.number) revert ForceIncludeBlockTooSoon();`) and never enforces the corresponding timestamp gate (`if (l1BlockAndTime[1] + delaySeconds >= block.timestamp) revert ForceIncludeTimeTooSoon();`). `delaySeconds` is a live, owner-set member of `MaxTimeVariation` (stored by `_setMaxTimeVariation`, consumed by `getTimeBounds`), and the `ForceIncludeTimeTooSoon` error is declared/imported but never thrown — confirming the time check was dropped while the rest of the contract still uses `delaySeconds`.
- Impact: Anyone (the path is permissionless) can force-include a delayed message once only the block window has elapsed, even though the configured wall-clock window has not. Whenever L1 produces `delayBlocks` blocks faster than `delaySeconds` implies, the sequencer's guaranteed exclusive ordering/reaction window collapses to the block bound alone, weakening censorship-resistance and increasing L2 reorg risk that the two-dimensional check was designed to prevent.
- Reviewer disagreement: One report (opus shot 2) found no vulnerabilities and characterized `forceInclusion` as adequately gated by "delay windows" alongside its cryptographic verification.

### `LOCAL_SET` one-step proof discards the local variable update
*(consensus, 3 of 6 reports)*
- Location: `src/osp/OneStepProver0.sol` : `executeLocalSet`
- Mechanism: `executeLocalSet` reads the current stack frame into a `StackFrame memory` copy, pops the new local value, and computes the updated `localsMerkleRoot`, but assigns it only to that memory copy. The updated frame is never written back into `mach.frameStack`, so the returned/proven post-state models `local.set` as "pop the stack value, leave the locals unchanged."
- Impact: The on-chain one-step prover accepts an incorrect transition for WASM `local.set`. A challenger/prover can confirm a length-one SmallStep edge whose post-state diverges from real WASM semantics (or reject a valid one), so `confirmEdgeByOneStepProof` can confirm the wrong edge — breaking fraud-proof soundness for any dispute reaching this instruction.

### Pre-funded ERC20 inbox balances can be consumed by any caller
*(consensus, 3 of 6 reports)*
- Location: `src/bridge/ERC20Inbox.sol` : `_deliverToBridge`
- Mechanism: `_deliverToBridge` pays `tokenAmount` out of the inbox contract's own native-token balance first, and only transfers the shortfall (`diff = tokenAmount - balanceOf(address(this))`) from `msg.sender` when the inbox balance is insufficient. No accounting ties prefunded tokens to the account that supplied them.
- Impact: If the inbox holds native tokens from an accidental transfer or any non-atomic prefunding flow, an attacker calling `depositERC20` or `createRetryableTicket` can have those tokens moved to the bridge to fund the attacker's chosen L2 credit/message — spending someone else's tokens. Precondition: the inbox holds native tokens before the attacker's call.

## Minority findings

### Timer cache can be credited from an unrelated claiming edge
*(minority, 1 of 6 reports)* *(conflicting reviews: 2 of 6 reports defended this code path)*
- Location: `src/challengeV2/libraries/EdgeChallengeManagerLib.sol` : `updateTimerCacheByClaim` / `checkClaimIdLink`
- Mechanism: `updateTimerCacheByClaim` is reachable via `EdgeChallengeManager.updateTimerCacheByClaim`, but `checkClaimIdLink` only verifies that the claiming edge's `originId` matches the lower edge's mutual id and that the level is correct. It never verifies `store.edges[claimingEdgeId].claimId == edgeId`, despite the `EdgeClaimMismatch` error being defined. Because all rivals share the same mutual id, a timer-cache credit from a higher-level edge that claims one rival can be applied to a different rival in the same mutual group.
- Impact: Any caller can incorrectly advance the cumulative timer cache of a rival edge that was not actually claimed. That poisoned cache is inherited by parent edges and can satisfy `confirmEdgeByTime`, allowing confirmation of the wrong challenge edge under normal challenge conditions.
- Reviewer disagreement: opus shots 1 and 3 reviewed the EdgeChallengeManager/BOLD edge accounting (stake routing, `setConfirmedRival`, `setRefunded`, timer-cache `uint64` handling) and judged it consistent with the audited reference, though neither singled out the missing `claimId` check in `checkClaimIdLink`.

### Staking pool credits deposits before verifying received tokens
*(minority, 1 of 6 reports)* *(conflicting reviews: 3 of 6 reports defended this code path)*
- Location: `src/assertionStakingPool/AbsBoldStakingPool.sol` : `depositIntoPool`
- Mechanism: `depositIntoPool` increments `depositBalance[msg.sender]` by the requested `amount` before calling `safeTransferFrom`, and records the requested amount rather than the actual balance delta received. With a callback-capable/malicious stake token the token can reenter after the balance is credited but before funds arrive; with a fee-on-transfer token the pool credits more than it actually receives.
- Impact: If a pool is configured with a non-standard or callback-capable stake token, an attacker can withdraw against unbacked credited balance or make the pool insolvent, draining tokens deposited by other users or returned from the rollup/challenge manager.
- Reviewer disagreement: opus shots 1, 2, and 3 examined this exact deposit/withdraw path and treated "update state before transferring" as correct checks-effects-interactions ordering — i.e., they cite the same ordering as a *defense* against reentrancy. They also note the non-standard-token risk is a documented trust assumption (non-rebasing / fee-free / callback-free token), not a vulnerability.

### Blob batch event can desync from the stored batch index
*(minority, 1 of 6 reports)*
- Location: `src/bridge/SequencerInbox.sol` : `addSequencerL2BatchFromBlobsImpl`
- Mechanism: The function obtains the canonical `seqMessageIndex` from `addSequencerL2BatchImpl` but emits the caller-supplied `sequenceNumber` in `SequencerBatchDelivered`. Because `sequenceNumber == type(uint256).max` bypasses the mismatch check, an accepted blob batch can report a batch number that does not match the stored sequencer accumulator index.
- Impact: An authorized batch poster can publish an accepted blob batch whose event reports a bogus sequence number, desynchronizing event-driven nodes or indexers that rely on `SequencerBatchDelivered` ordering. Precondition: attacker holds the batch-poster role.
- Reviewer disagreement: opus shot 1 reviewed SequencerInbox batch-count/delayed-message ordering checks and found them correct; opus shot 2 asserted "no event-vs-storage desync," but only with respect to the `OutBoxTransactionExecuted`/`StakeWithdrawn` events, not this blob-batch path.

---

*Reconciliation check: 14 finding-claims across 6 reports collapse to 6 distinct findings (by code path + root cause); 6 distinct findings emitted (3 consensus, 3 minority). No findings dropped.*

