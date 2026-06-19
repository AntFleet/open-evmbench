# Audit: 2024-03-gitcoin

## Missing `userTotalStaked` Accounting Update in `release`
- Location: `IdentityStaking.sol` : `release`
- Mechanism: When the `RELEASER_ROLE` releases previously slashed funds back to a staker, the function correctly restores the funds to the stake's `amount` field and reduces the `slashedAmount`. However, it fails to increment the `userTotalStaked[staker]` mapping by `amountToRelease`. The `userTotalStaked` mapping is decremented during the `slash` function but is never restored upon release.
- Impact: The `userTotalStaked` view function will permanently under-report the total staked balance for any user who has had slashed funds released. External protocols, dashboards, or internal logic (e.g., Passport scoring or voting power calculations) that rely on the `IIdentityStaking.userTotalStaked` interface will read incorrect, artificially lower balances for these users.

## Withdrawals Blocked Indefinitely When Contract is Paused
- Location: `IdentityStaking.sol` : `withdrawSelfStake`, `withdrawCommunityStake`
- Mechanism: Both `withdrawSelfStake` and `withdrawCommunityStake` are protected by the `whenNotPaused` modifier. If an admin with the `PAUSER_ROLE` pauses the contract, all withdrawal functionality is completely disabled, even for stakes that have already passed their `unlockTime` and are fully unlocked. 
- Impact: A malicious, compromised, or overly cautious admin can permanently freeze users' unlocked funds by pausing the contract. Best practice for pausable staking/locking contracts is to allow withdrawals of unlocked funds even during a pause, preventing the admin from holding user principal hostage.
