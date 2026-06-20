# Audit: 2023-12-ethereumcreditguild

Manual review found these genuine vulnerabilities:

## Rebasing self-transfer inflates CREDIT balance and voting power
- Location: `src/tokens/ERC20RebaseDistributor.sol` : `transfer`, `transferFrom`; `src/tokens/ERC20MultiVotes.sol` : `freeVotes`, `_incrementDelegation`
- Mechanism: Rebasing transfers handle sender and receiver share updates independently, but do not special-case `from == to`. A rebasing account can transfer CREDIT to itself; the sender branch subtracts shares, then the receiver branch overwrites the same account with shares calculated as if it received new tokens. `totalRebasingShares` is updated by a near-zero net delta, while the account’s `nShares` increases. `CreditToken.balanceOf()` then reports an inflated balance, and `ERC20MultiVotes.freeVotes()` trusts that inflated balance for delegation checkpoints.
- Impact: A CREDIT holder can inflate voting power without acquiring matching CREDIT, enabling veto/governance manipulation. The same broken share accounting can also let the attacker overclaim future rebasing rewards or make later reward materialization fail.

## New gauge voters can steal historical GUILD profit rewards
- Location: `src/governance/ProfitManager.sol` : `claimGaugeRewards`; `src/tokens/GuildToken.sol` : `_incrementGaugeWeight`
- Mechanism: `GuildToken._incrementGaugeWeight()` calls `ProfitManager.claimGaugeRewards(user, gauge)` before increasing the user’s gauge weight. For a user with zero current weight, `claimGaugeRewards()` returns immediately and does not initialize `userGaugeProfitIndex[user][gauge]` to the current `gaugeProfitIndex`. After the new weight is added, the user’s profit index remains zero and is later treated as `1e18`, so the user is credited for all historical index growth.
- Impact: An attacker can add GUILD weight to a gauge after profits were already reported, then claim CREDIT rewards as if they had voted for that gauge the whole time. This drains ProfitManager-held CREDIT from rightful gauge voters and can make legitimate claims revert once funds are exhausted.

## Insolvent loss reporting can revert and permanently block loan closure
- Location: `src/governance/ProfitManager.sol` : `notifyPnL`; `src/loan/LendingTerm.sol` : `onBid`
- Mechanism: For losses larger than the surplus buffers, `notifyPnL()` computes `creditTotalSupply - loss` without handling the case where the remaining CREDIT supply is smaller than the loss. A borrower can borrow CREDIT, redeem or otherwise remove it from supply, then default. When the auction closes with insufficient recovery, `LendingTerm.onBid()` calls `notifyPnL()` with a loss that can exceed the current CREDIT supply, causing an underflow or division-by-zero revert.
- Impact: Bad debt cannot be recognized, the auction callback reverts, the loan remains unclosed, issuance stays stuck, and offboarding/cleanup for the affected term can be blocked.

## Historical gauge loss incorrectly slashes later SurplusGuildMinter stakers
- Location: `src/loan/SurplusGuildMinter.sol` : `getRewards`
- Mechanism: `getRewards()` checks `lastGaugeLoss > uint256(userStake.lastGaugeLoss)` before loading `userStake = _stakes[user][term]`. Because the memory return variable is still zeroed at that point, any term with any historical loss sets `slashed = true` for every caller, even users who staked after that loss and stored the latest loss timestamp.
- Impact: After a term has one loss, any later SurplusGuildMinter staker can be falsely slashed on `unstake()`, `getRewards()`, or `updateMintRatio()`. Their staking accounting is zeroed and their CREDIT contribution is forfeited, allowing a dust loss to permanently grief future SGM staking for that term.

## Offboarding approval never expires
- Location: `src/governance/LendingTermOffboarding.sol` : `supportOffboard`, `offboard`
- Mechanism: `supportOffboard()` sets `canOffboard[term] = true` once any poll reaches quorum, but `offboard()` only checks that boolean and does not bind execution to the poll’s `snapshotBlock` or `POLL_DURATION_BLOCKS`. The approval is also not cleared when the poll expires.
- Impact: A stale successful poll can be executed long after the intended voting window, including after conditions changed or after a term was re-onboarded. Anyone can later offboard the term without fresh quorum.

