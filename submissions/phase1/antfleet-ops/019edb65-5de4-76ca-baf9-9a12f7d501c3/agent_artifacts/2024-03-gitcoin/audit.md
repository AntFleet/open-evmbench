# Audit: 2024-03-gitcoin

## Missing userTotalStaked update in `release`
- **Location:** `IdentityStaking.sol` : `release` function
- **Mechanism:** The `release` function moves a slashed amount back from `slashedAmount` to `amount` on a user’s stake (self or community). However, it never increments the `userTotalStaked` mapping for the staker. A slash previously decremented `userTotalStaked` by the slashed amount, so after a release the mapping remains permanently lower than the true total of the user’s stake amounts.
- **Impact:** Any on-chain or off-chain logic that consumes `userTotalStaked` (as defined in `IIdentityStaking`) will see an incorrect, understated value for the affected staker. This can lead to loss of voting power, rewards, or other benefits that depend on the total staked balance.
