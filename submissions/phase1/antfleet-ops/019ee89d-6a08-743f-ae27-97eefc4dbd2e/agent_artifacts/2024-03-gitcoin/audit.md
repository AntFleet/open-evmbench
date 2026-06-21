# Audit: 2024-03-gitcoin

## release() never restores userTotalStaked, locking appealed funds
- Location: id-staking-v2/contracts/IdentityStaking.sol : release
- Mechanism: `slash()` decrements `userTotalStaked[staker]` by `slashedAmount` at the same time it reduces `sStake.amount`, preserving the invariant `userTotalStaked == Σ(stake amounts)`. The reverse operation `release()` increases `selfStakes[staker].amount` (or `communityStakes[staker][stakee].amount`) and decreases `slashedAmount`/`totalSlashed[slashRound]`, but it never re-increments `userTotalStaked[staker]`. After a slash followed by a release, `userTotalStaked` is permanently lower than the sum of the user's restored stake amounts. Since `withdrawSelfStake`/`withdrawCommunityStake` perform `userTotalStaked[msg.sender] -= amount` under 0.8.x checked arithmetic, once the restored `amount` exceeds the under-counted `userTotalStaked`, the withdrawal underflows and reverts.
- Impact: GTC returned to a slashed staker through a legitimate appeal becomes permanently un-withdrawable (the released delta is locked), and the public `userTotalStaked` view under-reports stake, corrupting any downstream Passport scoring that consumes it.

## slash() amount calculation overflows uint88 for large stakes
- Location: id-staking-v2/contracts/IdentityStaking.sol : slash
- Mechanism: For each victim the slash amount is computed as `uint88 slashedAmount = (percent * selfStakes[staker].amount) / 100;` (and the analogous community line). Both `percent` and `amount` are `uint88`, so the product `percent * amount` is evaluated in `uint88` arithmetic *before* the division. With `percent` up to 100 and `amount` up to roughly `uint88` max (≈3.09e26, ~309M GTC by the contract's own comment), the intermediate product can reach ~3e28 and overflow `uint88`, which reverts under Solidity 0.8.x checked math. Any single stake above ~3.09e24 (≈3.09M GTC) cannot be slashed at 100% (proportionally smaller percents overflow for larger stakes). Because `slash` processes the `selfStakers`/`communityStakers` arrays atomically, a single oversized stake in the batch reverts the entire slashing transaction.
- Impact: Large stakers become effectively un-slashable at meaningful percentages, and one oversized stake placed by an attacker can deny-of-service an entire slashing batch.

