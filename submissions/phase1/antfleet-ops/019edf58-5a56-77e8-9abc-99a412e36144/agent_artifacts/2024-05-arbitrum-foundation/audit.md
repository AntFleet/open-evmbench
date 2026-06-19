# Audit: 2024-05-arbitrum-foundation

# Security Audit Report

After a thorough review of the codebase, here are the findings:

## CEI Violation in depositIntoPool
- **Location**: `src/assertionStakingPool/AbsBoldStakingPool.sol` : `depositIntoPool`
- **Mechanism**: The function credits `depositBalance[msg.sender] += amount` **before** calling `IERC20(stakeToken).safeTransferFrom(msg.sender, address(this), amount)`. This violates the Checks-Effects-Interactions pattern. While standard ERC20 tokens do not invoke callbacks during `transferFrom`, non-standard tokens (e.g., ERC-777 with `tokensToSend` hooks, or custom tokens with sender-side transfer callbacks) could reenter `depositIntoPool` or `withdrawFromPool` during the transfer. The pool contract has no `receive`/`fallback` and doesn't implement `IERC777Recipient`, which mitigates most callback vectors, but the pattern is still unsafe for arbitrary token implementations.
- **Impact**: With the specific stake tokens assumed by the protocol (standard ERC20), this is not practically exploitable. However, if the stake token were ever changed to one with transfer callbacks, a reentrancy attack could allow a depositor to be credited an inflated `depositBalance` or to withdraw funds they are not entitled to during the deposit transfer. The `withdrawFromPool` function correctly follows CEI (debits before transfer), so only the deposit path is affected.

## Unrestricted createAssertion / createEdge with Front-Running Excess Approval
- **Location**: `src/assertionStakingPool/AssertionStakingPool.sol` : `createAssertion` and `src/assertionStakingPool/EdgeStakingPool.sol` : `createEdge`
- **Mechanism**: Both functions are callable by anyone (by design, as trustless pools). `createAssertion` calls `safeIncreaseAllowance(rollup, requiredStake)` before `newStakeOnNewAssertion`. `createEdge` calls `safeIncreaseAllowance(challengeManager, requiredStake)` before `createLayerZeroEdge`. If the underlying rollup/challenge-manager call reverts after the allowance increase (e.g., due to a transient condition or front-running), the transaction reverts entirely so no lingering approval remains. However, if the call succeeds but a second call is made (e.g., by a different caller front-running with different inputs that still match the immutable hash), the `safeIncreaseAllowance` accumulates, leaving a residual approval to the rollup/challenge manager. The rollup/challenge manager is the only entity that can draw on this allowance, and it only draws what is needed for staking, so the excess is not directly stealable — but it represents an accounting irregularity where the pool grants more allowance than it intends.
- **Impact**: An attacker cannot steal funds directly, but repeated successful `createAssertion`/`createEdge` calls (if the underlying protocol allows re-calling without reverting on duplicate) could leave the pool with an inflated allowance to the rollup/challenge manager. In practice, the rollup rejects duplicate assertions and the edge manager rejects duplicate edges, so the second call reverts and the allowance increase is rolled back. This is a low-severity concern dependent on the external contract's behavior.

## createEdge Stake Amount Mismatch on Level Disagreement
- **Location**: `src/assertionStakingPool/EdgeStakingPool.sol` : `createEdge`
- **Mechanism**: The function reads `requiredStake = EdgeChallengeManager(challengeManager).stakeAmounts(args.level)` and approves that amount, then calls `createLayerZeroEdge(args)` which internally uses `stakeAmounts[args.level]` for the actual transfer. If `args.level` is out of bounds, `stakeAmounts` reverts. If `args.level` is valid but the resulting edge ID doesn't match the pool's immutable `edgeId`, the function reverts with `IncorrectEdgeId`. The approved amount and the transferred amount always come from the same `stakeAmounts[args.level]` lookup, so they are consistent. No mismatch occurs in practice.
- **Impact**: No exploitable vulnerability — the revert on edge ID mismatch ensures consistency. Listed for completeness as the approval and transfer are in separate external calls.

---

**Summary**: The codebase is well-secured with appropriate access controls, CEI patterns (with the one exception noted above), checked arithmetic, and comprehensive validation. The bridge/inbox/outbox system correctly handles reentrancy via context save/restore and active-outbox tracking. The challenge manager's edge lifecycle, staking, and confirmation logic is sound. No critical or high-severity vulnerabilities were identified.
