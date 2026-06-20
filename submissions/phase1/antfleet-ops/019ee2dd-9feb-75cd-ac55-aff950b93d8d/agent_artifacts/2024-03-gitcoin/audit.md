# Audit: 2024-03-gitcoin

 ## Released slashes are not restored to `userTotalStaked`
- Location: `id-staking-v2/contracts/IdentityStaking.sol` : `release`
- Mechanism: When `release` returns slashed funds to a stake, it restores `Stake.amount` and decrements `Stake.slashedAmount`, but it never reverses the `userTotalStaked[staker] -= slashedAmount` update that `slash` performed. As a result, the `userTotalStaked` tracker permanently diverges from the actual sum of active stake amounts.
- Impact: After being slashed and then released, a user’s recorded `userTotalStaked` is lower than the real amount stored in `selfStakes`/`communityStakes`. Withdrawing the full restored amount then underflows `userTotalStaked -= amount`, reverting and locking the released portion of the funds. External consumers of `userTotalStaked()` also receive a deflated, incorrect stake value.

## Duplicate `slash` targets bypass the percentage cap
- Location: `id-staking-v2/contracts/IdentityStaking.sol` : `slash`
- Mechanism: `slash` only validates that `percent <= 100` once and does not de-duplicate the `selfStakers` or `communityStakers`/`communityStakees` arrays. If the same staker/stakee pair appears multiple times, each iteration recomputes the slash on the remaining `amount`, applying the percentage repeatedly.
- Impact: A compromised or malicious address with `SLASHER_ROLE` can confiscate far more than the intended `percent` of a victim’s stake in a single transaction (up to effectively 100% by repeating the address), defeating the protocol’s slash-size limit and seizing excessive user funds.

## Uninitialized UUPS implementation and front-runnable `initialize`
- Location: `id-staking-v2/contracts/IdentityStaking.sol` : `initialize` (no constructor with `_disableInitializers`)
- Mechanism: `IdentityStaking` is a UUPS upgradeable contract but has no constructor that calls `_disableInitializers()`, and `initialize` is public and unguarded during the initialization window. If the proxy deployment and `initialize` call are not atomic, an attacker can call `initialize` first and grant themselves `DEFAULT_ADMIN_ROLE` and `PAUSER_ROLE`.
- Impact: The attacker becomes the proxy’s admin and can authorize upgrades, replacing the implementation with a malicious contract to drain all staked GTC, pause/unpause at will, or lock the protocol. Even with atomic proxy initialization, the standalone implementation remains initialize-able by anyone, violating the standard UUPS security pattern.
