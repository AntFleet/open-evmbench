# Audit: 2024-03-gitcoin

Here is the audit report for the provided Solidity codebase.

## Missing `userTotalStaked` restoration in `release` leads to locked funds, deniable slashes, and inaccurate reputation scores
- **Location**: `IdentityStaking.sol` : `release`
- **Mechanism**: When a slash occurs via `slash()`, the user's active stake amount is decreased (`amount -= slashedAmount`), and their total staked tracking mapping is also decremented (`userTotalStaked[staker] -= slashedAmount`). However, when a slash is subsequently approved for release (appealed) via the `release()` function, the contract only restores the stakeholder's individual stake (`selfStakes[staker].amount += amountToRelease` or `communityStakes[staker][stakee].amount += amountToRelease`). It completely omits updating and incrementing the `userTotalStaked[staker]` state variable back by the released amount.
- **Impact**: 
  1. **Permanent Lock of Restored Funds**: When the user attempts to withdraw their restored stake (via `withdrawSelfStake()` or `withdrawCommunityStake()`), the contract executes `userTotalStaked[msg.sender] -= amount`. Because `userTotalStaked` was never restored during the release step, this subtraction will underflow and revert in Solidity 0.8.23, permanently trapping the user's released funds in the contract.
  2. **Deniable future slashes (Bulk DoS)**: If a desynced user is slashed again in a future round, the `userTotalStaked[staker] -= slashedAmount` operation inside `slash()` will underflow and revert. Because slashing is typically executed in bulk arrays (`selfStakers`, `communityStakers`), a single affected user can cause the entire batch slash transaction to revert, blocking the `SLASHER_ROLE` from performing their duties.
  3. **Inaccurate Passport Scoring**: External integrations consuming `userTotalStaked()` to rate a user's trust, reputation, or sybil-resistance score will receive a permanently de-synced (lower-than-actual) representation of the user's active stake.
