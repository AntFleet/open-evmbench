# Audit: 2024-03-gitcoin

## Slash arithmetic overflows on large stakes
- Location: `id-staking-v2/contracts/IdentityStaking.sol` : `slash()`
- Mechanism: `slash()` computes `slashedAmount` as `(percent * selfStakes[staker].amount) / 100` and `(percent * communityStakes[staker][stakee].amount) / 100`, then stores the result in `uint88`. Because both operands are `uint88`, the multiplication is performed in 88-bit arithmetic and reverts before the division when `amount > type(uint88).max / percent`. That threshold is realistic for this token: at `percent = 100`, any stake above about `3.09M` tokens overflows; at lower percentages, larger but still realistic stakes overflow as well. Since the overflow happens inside the loop, a single oversized stake makes the entire slash transaction revert.
- Impact: Large stakers can become partially or fully unslashable. A slashing operation that includes one oversized stake will fail atomically, letting whale positions evade intended penalties and causing enforcement DoS for that batch.

## Released stake can become permanently unwithdrawable
- Location: `id-staking-v2/contracts/IdentityStaking.sol` : `slash()`, `release()`, `withdrawSelfStake()`, `withdrawCommunityStake()`
- Mechanism: `slash()` decreases `userTotalStaked[staker]` when funds are slashed, and both withdraw functions later decrease `userTotalStaked[msg.sender]` again on withdrawal. But `release()` only restores the per-stake `amount` field (`selfStakes[staker].amount` or `communityStakes[staker][stakee].amount`) and decreases `totalSlashed[slashRound]`; it never adds the released amount back to `userTotalStaked`. After a release, the stake principal is restored but the aggregate accounting stays too low. When the user later withdraws the restored amount, `userTotalStaked[msg.sender] -= amount` eventually underflows and reverts, even though the stake’s own `amount` is sufficient.
- Impact: Any released slash can lock some or all of the restored stake permanently, causing a direct funds-withdrawal DoS for the affected staker. It also makes `userTotalStaked()` report a persistently incorrect lower value to downstream consumers.

Assumption: I treated `contracts/test_mocks/*` as non-production based on their inline headers and did not count their intentional insecurities as audit findings.

