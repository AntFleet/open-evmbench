# Audit: 2024-03-gitcoin

## Released stake is not restored to `userTotalStaked`
- Location: `id-staking-v2/contracts/IdentityStaking.sol` : `release`
- Mechanism: `slash()` reduces both the per-stake `amount` and `userTotalStaked[staker]`, but `release()` only restores the per-stake `amount` by incrementing `selfStakes[staker].amount` or `communityStakes[staker][stakee].amount`. It never performs the matching `userTotalStaked[staker] += amountToRelease`.
- Impact: Released funds can become permanently unwithdrawable. Example: a user stakes 100, is slashed 50, then has 50 released. Their stake `amount` returns to 100, but `userTotalStaked` remains 50. A withdrawal of 100 passes the per-stake amount check, then underflows on `userTotalStaked[msg.sender] -= amount` and reverts; withdrawing only 50 leaves the released 50 stuck.

## Large stake slashing overflows before division
- Location: `id-staking-v2/contracts/IdentityStaking.sol` : `slash`
- Mechanism: The slash amount is computed as `(percent * selfStakes[staker].amount) / 100` and similarly for community stakes. Both operands are `uint88`, so the multiplication is checked in `uint88` before the division. For large stakes, `percent * amount` overflows even though the final percentage result would fit.
- Impact: Large stakers can become impossible to slash at intended percentages. A 100% slash reverts for any stake above roughly `type(uint88).max / 100`, about 3.09M tokens with 18 decimals. One oversized stake in a slash batch reverts the whole transaction, blocking enforcement for that batch.

