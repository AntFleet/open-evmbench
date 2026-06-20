# Audit: 2024-05-arbitrum-foundation

## Required-stake decrease can make old stakers withdraw slashed stake

- Location: `src/rollup/RollupCore.sol` : `requireInactiveStaker`; `src/rollup/RollupUserLogic.sol` : `stakeOnNewAssertion`, `reduceDeposit`, `returnOldDeposit`
- Mechanism: `requireInactiveStaker` treats a staker as inactive when their latest staked assertion merely has a child. Separately, `stakeOnNewAssertion` allows a staker whose latest assertion has a child to move to another branch, and losing sibling stake is transferred to `loserStakeEscrow` without reducing the staker’s recorded `amountStaked`. If `baseStake` is lowered after an older assertion was created, an attacker can create a rival child that still requires the old higher stake, have an accomplice create a low-stake child under it using the newer lower `requiredStake`, and then become “inactive” because their assertion has a child.
- Impact: The attacker can withdraw or reduce the old high recorded stake even though that stake was already swept to `loserStakeEscrow`, leaving the rollup undercollateralized. Honest validators can become unable to recover their stake because the rollup’s token balance no longer covers recorded staker balances.

## `LOCAL_SET` one-step proof does not update the frame locals root

- Location: `src/osp/OneStepProver0.sol` : `executeLocalSet`
- Mechanism: `executeLocalSet` pops the new local value and calls `mach.frameStack.peek()`, but `peek()` returns a memory copy of the single proved `StackFrame`. The function updates `frame.localsMerkleRoot` on that copy and never writes it back into `mach.frameStack.proved[0]`. The returned machine hash therefore represents a transition where the stack was popped but the local variable root was not changed.
- Impact: A challenger can prove an invalid WASM transition for any disputed step containing `LOCAL_SET`. Since `confirmEdgeByOneStepProof` trusts `proveOneStep`, this can confirm the wrong challenge edge and allow an invalid assertion path to win.

## Rival edge timer cache can be credited through the wrong claim edge

- Location: `src/challengeV2/libraries/EdgeChallengeManagerLib.sol` : `updateTimerCacheByClaim`
- Mechanism: `updateTimerCacheByClaim(edgeId, claimingEdgeId)` is meant to add timer cache from a zero-layer edge that actually claims `edgeId`. However, `checkClaimIdLink` only verifies that `claimingEdgeId.originId == edgeId.mutualId()` and that the levels are adjacent. It never checks `store.edges[claimingEdgeId].claimId == edgeId`. Rival lower-level edges share the same `mutualId`, so a claiming edge for one rival can be used to update the timer cache of another rival.
- Impact: An attacker can misattribute accumulated unrivaled time from one branch to a different rival branch, propagate that forged cache upward through `timeUnrivaledTotal`, and satisfy `confirmEdgeByTime` for the wrong edge, breaking challenge resolution.

