# Audit: 2024-03-gitcoin

## Released stake is not restored to `userTotalStaked`
- Location: `id-staking-v2/contracts/IdentityStaking.sol` : `release`
- Mechanism: `slash()` reduces both the per-stake `amount` and `userTotalStaked[staker]`, but `release()` only restores the per-stake `amount`. It never performs the matching `userTotalStaked[staker] += amountToRelease`. After a slash-and-release cycle, the stake record says the user has more withdrawable stake than the aggregate accounting allows.
- Impact: Released funds can become permanently stuck. Example: stake 100, slash 50, release 50. The stake `amount` is back to 100, but `userTotalStaked` remains 50. Withdrawing 100 underflows and reverts; withdrawing 50 leaves the released 50 trapped. Future slashes can also underflow and revert, making affected stakes partially unslashable and causing batch slash DoS.

## Large stake slashing overflows before division
- Location: `id-staking-v2/contracts/IdentityStaking.sol` : `slash`
- Mechanism: The slashed amount is computed as `(percent * selfStakes[staker].amount) / 100` and similarly for community stakes. Both operands are `uint88`, so Solidity performs the multiplication in `uint88` before dividing. For large stakes, `percent * amount` overflows even though the final divided result would fit.
- Impact: Large stakers can become impossible to slash at intended percentages. For a 100% slash, any stake above roughly `type(uint88).max / 100` reverts the slash. One oversized stake in the input arrays reverts the entire batch, blocking slashing for other users in that transaction.

## Uninitialized proxy can be seized during non-atomic deployment
- Location: `id-staking-v2/contracts/IdentityStaking.sol` : `initialize`
- Mechanism: `initialize()` is public and grants `DEFAULT_ADMIN_ROLE` to the caller-supplied `initialAdmin`. If the proxy is deployed without atomically calling `initialize`, anyone can front-run initialization and set themselves or an accomplice as admin. The function also does not reject `initialAdmin == address(0)`, which can permanently brick admin control.
- Impact: An attacker who initializes first gains upgrade authority over the UUPS proxy and can deploy malicious logic controlling staked funds. A zero admin misconfiguration permanently removes upgrade and pause administration.

