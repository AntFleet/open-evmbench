# Audit: 2023-12-ethereumcreditguild

# Security Audit Report

## ERC20Gauges._decrementWeightUntilFree infinite loop with zero-weight gauges
- Location: `src/tokens/ERC20Gauges.sol` : `_decrementWeightUntilFree`
- Mechanism: The loop increments `i` only inside the `if (userGaugeWeight != 0)` block. If a user has a gauge in their `_userGauges` set with 0 allocated weight (achievable by calling `incrementGauge(gauge, 0)` or `incrementGauges` with a zero entry), the loop variable `i` never advances past that gauge, creating an infinite loop that consumes all gas. The gauge remains in the set because `_decrementGaugeWeight` only removes it when `oldWeight == weight`, and the loop skips 0-weight gauges entirely.
- Impact: Any GUILD holder who has a zero-weight gauge in their set will have all token transfers, burns, and gauge-loss applications that require freeing weight permanently revert (out of gas). This permanently locks their GUILD tokens. The affected functions include `transfer`, `transferFrom`, `_burn` (used by `applyGaugeLoss`), and any operation that triggers `_decrementWeightUntilFree`. The user can only recover by removing the zero-weight gauge via `decrementGauge(gauge, 0)`, which itself may fail if the gauge has a pending loss or outstanding issuance (due to the GuildToken override checks).

## GuildToken._decrementGaugeWeight makes external calls during token transfers
- Location: `src/tokens/GuildToken.sol` : `_decrementGaugeWeight` (override)
- Mechanism: The overridden `_decrementGaugeWeight` calls `ProfitManager(profitManager).claimGaugeRewards(user, gauge)` (which transfers CREDIT to the user) and `LendingTerm(gauge).issuance()` / `LendingTerm(gauge).debtCeiling(...)` during gauge weight freeing, which is triggered inside `_decrementWeightUntilFree` during `transfer`, `transferFrom`, and `_burn`. If any gauge the sender votes for has active issuance that exceeds the post-decrement debt ceiling, the `require(issuance <= debtCeilingAfterDecrement)` check fails and the entire token transfer reverts.
- Impact: GUILD token transfers can be blocked by any gauge the sender has voted for having outstanding loans near its debt ceiling. A sender cannot transfer or burn their GUILD tokens until they either call loans on the affected lending terms (to reduce issuance below the debt ceiling) or remove their gauge weight — which itself requires passing the same check. In edge cases (e.g., a deprecated gauge with outstanding issuance where `debtCeiling` returns 0), the user's GUILD may be permanently locked until all loans on that term are closed.

## LendingTermOffboarding.supportOffboard allows unrestricted multi-poll voting
- Location: `src/governance/LendingTermOffboarding.sol` : `supportOffboard`
- Mechanism: A user's voting weight (`getPastVotes`) is applied fully to each offboarding poll independently. There is no global cap tracking how much of a user's voting power has been "spent" across polls. A user with X voting power can support the offboarding of every term simultaneously, each with full weight X. This contrasts with the gauge system where total allocated weight is capped by token balance.
- Impact: A minority GUILD holder (or coalition) whose voting power is below quorum for any single term can nonetheless meet quorum for offboarding multiple terms simultaneously, since their full weight counts toward each poll. This could enable offboarding of multiple lending terms (pausing PSM redemptions and preventing new loans) with less collective support than the quorum threshold implies per-term.

## SurplusGuildMinter.getRewards transfers CREDIT rewards to slashed users before zeroing stake
- Location: `src/loan/SurplusGuildMinter.sol` : `getRewards`
- Mechanism: When a gauge loss is detected (`slashed == true`), the function still transfers `creditReward` (CREDIT profit from the gauge) to the user before zeroing out their stake. The `guildReward` is correctly set to 0 for slashed users, but the CREDIT reward is not. The user's staked CREDIT (donated to the term surplus buffer) is forfeited, but pending CREDIT profits are still collected.
- Impact: Slashed users receive CREDIT rewards that were accrued from the gauge's profit index, even though their position is being penalized for the gauge's loss. While the forfeited CREDIT surplus buffer contribution may exceed the CREDIT rewards in practice, the code does not enforce this invariant. An attacker who stakes right before a loss could capture a disproportionate share of previously-accrued profits.
