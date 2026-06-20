# Audit: 2024-03-gitcoin

## Slashing can revert for large stakes due to `uint88` multiplication overflow
- Location: `id-staking-v2/contracts/IdentityStaking.sol` : `slash`
- Mechanism: `slashedAmount` is computed as `(percent * stake.amount) / 100` where both `percent` and `amount` are `uint88`. Solidity checks overflow at the operand type width, so the multiplication can revert before division. For a 100% slash, any stake above roughly `type(uint88).max / 100` cannot be slashed.
- Impact: A large staker can make high-percentage slashes against their stake impossible, causing the entire slash transaction to revert whenever their stake is included. This lets large positions resist intended slashing or force slashers to use much smaller percentages.

## Released slashed stake is restored without restoring total-staked accounting
- Location: `id-staking-v2/contracts/IdentityStaking.sol` : `release`
- Mechanism: `slash` reduces both the stake’s `amount` and `userTotalStaked[staker]`. `release` adds the released amount back to `selfStakes[staker].amount` or `communityStakes[staker][stakee].amount`, but never increments `userTotalStaked[staker]`.
- Impact: After a release, `userTotalStaked` permanently understates the staker’s actual withdrawable stake. When the staker later withdraws the restored amount, `userTotalStaked[msg.sender] -= amount` can underflow and revert, effectively locking the released stake or breaking downstream consumers that rely on `userTotalStaked`.

I did not count the `test_mocks` contracts as production vulnerabilities because they are explicitly marked non-production test code.

