# Audit: 2023-12-ethereumcreditguild

## Late gauge voters can claim historical rewards
- Location: `src/governance/ProfitManager.sol` : `claimGaugeRewards`; `src/tokens/GuildToken.sol` : `_incrementGaugeWeight`
- Mechanism: When a user has zero weight in a gauge, `claimGaugeRewards` returns before initializing `userGaugeProfitIndex[user][gauge]`. `GuildToken._incrementGaugeWeight` calls `claimGaugeRewards` before adding new gauge weight, so a first-time voter’s index remains zero. On the next claim, zero is treated as `1e18`, allowing the new voter to earn rewards from all prior `gaugeProfitIndex` growth.
- Impact: An attacker can vote into a gauge after profits have accrued and claim historical rewards they did not earn, draining CREDIT rewards from the ProfitManager.

## Rebasing self-transfer mints other users’ pending rewards
- Location: `src/tokens/ERC20RebaseDistributor.sol` : `transfer`, `transferFrom`
- Mechanism: The rebase transfer logic caches sender and recipient rebasing state before the transfer. If `from == to`, the sender path updates the account’s shares, then the recipient path uses the stale pre-transfer share count and treats the self-transfer amount as an added balance. That can materialize unminted rebase rewards to the same account.
- Impact: A rebasing CREDIT holder can repeatedly self-transfer to mint a disproportionate share of pending distributed rewards, stealing rewards owed to other rebasing holders.

## SurplusGuildMinter slashes valid post-loss stakes
- Location: `src/loan/SurplusGuildMinter.sol` : `getRewards`
- Mechanism: `getRewards` compares `GuildToken.lastGaugeLoss(term)` against `userStake.lastGaugeLoss` before loading `userStake = _stakes[user][term]`. The in-memory `userStake.lastGaugeLoss` is therefore always zero at the comparison. After any historical loss on a term, every later stake on that term is considered slashed even if it was opened after the loss and stored the correct loss timestamp.
- Impact: Anyone can call `getRewards(victim, term)` or trigger it through related flows and wipe a legitimate staker’s position, preventing withdrawal of their CREDIT stake and burning their synthetic GUILD exposure.

## Offboarding quorum never expires after it is reached
- Location: `src/governance/LendingTermOffboarding.sol` : `supportOffboard`, `offboard`
- Mechanism: `supportOffboard` enforces `POLL_DURATION_BLOCKS` only while adding votes. Once quorum is reached it sets `canOffboard[term] = true`, and `offboard` later checks only that boolean with no snapshot-block or expiry validation.
- Impact: A term that once reached offboarding quorum can be removed by anyone at any future time, even after market conditions and voter preferences changed. This can disable new loans for an active term, force loan call flows, and pause PSM redemptions.

## Loss slashing can be blocked by the debt-ceiling guard
- Location: `src/tokens/GuildToken.sol` : `applyGaugeLoss`, `_decrementGaugeWeight`
- Mechanism: `applyGaugeLoss` is intended to forcibly slash users voting for a lossy gauge, but it reuses `_decrementGaugeWeight`, which includes the voluntary-exit debt-ceiling check. If removing the user’s weight would make current `LendingTerm.issuance()` exceed `debtCeiling(-weight)`, the slash reverts before the gauge weight is removed and before GUILD is burned.
- Impact: Voters backing a lossy, utilized term can be impossible to slash while issuance remains high, delaying or preventing first-loss enforcement and leaving gauge weight/accounting overstated after bad debt.

## Bad-debt realization can revert when loss exceeds CREDIT supply
- Location: `src/governance/ProfitManager.sol` : `notifyPnL`; `src/loan/LendingTerm.sol` : `onBid`, `forgive`
- Mechanism: After surplus buffer depletion, `notifyPnL` computes `creditTotalSupply - loss` without capping the loss to available supply. CREDIT is publicly burnable and can also be redeemed through the PSM, so the remaining CREDIT supply can be lower than the principal loss being reported. In that case `notifyPnL` underflows and reverts, rolling back `onBid` or `forgive`.
- Impact: A borrower can reduce circulating CREDIT after borrowing, then default in a way that makes bad-debt accounting unexecutable. The affected loan cannot be closed through auction loss reporting or forgiveness, leaving issuance and liquidation state stuck.

