# Audit: 2023-12-ethereumcreditguild

# Ethereum Credit Guild — Security Audit Report

## Incorrect slash check uses uninitialized stake in `getRewards`
- Location: `src/loan/SurplusGuildMinter.sol` : `getRewards`
- Mechanism: The slash predicate compares `GuildToken.lastGaugeLoss(term)` against `userStake.lastGaugeLoss` before `userStake` is loaded from `_stakes[user][term]`. In memory, `userStake` is zero-initialized, so `userStake.lastGaugeLoss` is always `0`. Whenever a gauge has ever recorded a loss (`lastGaugeLoss > 0`), `slashed` is set to `true` for every user on that term, including users who staked after the loss and correctly recorded `lastGaugeLoss` during `stake()`. On a later call when `stakeTime != 0`, the slash branch zeroes the user’s stake without withdrawing their CREDIT from `termSurplusBuffer`, decrementing `SurplusGuildMinter`’s gauge weight, or burning its GUILD.
- Impact: Any address can call the public `getRewards(user, term)` to grief stakers on any term that has ever had bad debt. Victims lose their accounting position, cannot `unstake` (stake is cleared while buffer funds remain), and may still lose forfeited CREDIT to the protocol. This breaks the core `SurplusGuildMinter` staking/unstaking flow.

## Bad-debt haircut understates losses by using inflated CREDIT supply
- Location: `src/governance/ProfitManager.sol` : `notifyPnL`
- Mechanism: When a loss exceeds the surplus buffer, `creditMultiplier` is updated using `CreditToken.totalSupply()`, which (via `ERC20RebaseDistributor`) equals `ERC20.totalSupply() + unmintedRebaseRewards()`. The `loss` amount reflects realized bad principal in circulation, but the denominator also includes not-yet-minted rebasing rewards. That makes `(creditTotalSupply - loss) / creditTotalSupply` larger than it should be, so the multiplier drops less than required to absorb the loss.
- Impact: After large bad-debt events, CREDIT holders and the protocol absorb less of the loss than intended. The system can remain undercollateralized relative to outstanding loan principal, and lenders/rebasing participants bear an incorrect share of insolvency risk.

## Guild profit share can become permanently stranded
- Location: `src/governance/ProfitManager.sol` : `notifyPnL`
- Mechanism: On profit notification, the `amountForGuild` slice is only credited to `gaugeProfitIndex` when `GuildToken.getGaugeWeight(gauge) != 0`. If all GUILD weight has been removed from a gauge (e.g., after offboarding, loss application, or voters reallocating) at the moment interest is reported, the index is not updated and those CREDIT tokens are never allocated to `distribute`, `transfer` to `otherRecipient`, or added to `surplusBuffer`.
- Impact: CREDIT profit intended for GUILD voters can remain stuck on `ProfitManager` with no accounting path to distribute it, effectively locking protocol revenue and breaking profit-sharing guarantees.

## Zero-weight gauge entries can brick GUILD transfers and burns
- Location: `src/tokens/ERC20Gauges.sol` : `_decrementWeightUntilFree`
- Mechanism: `incrementGauge` / `_incrementGaugeWeight` allow `weight == 0` and still call `_userGauges[user].add(gauge)`, leaving a gauge in the user’s set with zero allocated weight. `_decrementWeightUntilFree` only increments its loop index when `userGaugeWeight != 0`. If the user needs to free weight (transfer/burn) and such a zero-weight entry is encountered before enough weight is freed, the loop never advances and the transaction runs out of gas.
- Impact: A user (or contract such as `SurplusGuildMinter` when `mintRatio` is `0` and `incrementGauge(term, 0)` is called) can permanently DoS their own `GuildToken` transfers and burns. Any integration that relies on moving or burning GUILD from that address becomes unusable.

## Rebasing first-depositor share inflation is not mitigated in code
- Location: `src/tokens/ERC20RebaseDistributor.sol` : `enterRebase` / `distribute`
- Mechanism: The contract documents the classic first-depositor inflation attack (similar to the Hundred Finance exploit): a user with a tiny rebasing balance can manipulate the rebasing share price so a later large `distribute()` disproportionately benefits them. The comments recommend keeping a minimum rebasing balance, but no on-chain minimum or seeding enforcement exists.
- Impact: An early attacker can steal a large fraction of future CREDIT savings-rate distributions from honest rebasing holders, undermining the protocol’s lender-yield mechanism.

## Fee-on-transfer or deflationary collateral breaks lending accounting
- Location: `src/loan/LendingTerm.sol` : `_borrow`, `_addCollateral`, `onBid`
- Mechanism: Collateral intake uses `safeTransferFrom` and records the requested `collateralAmount` without verifying the contract’s actual balance increase. `LendingTermOnboarding.createTerm` only checks that `collateralToken` responds to `totalSupply()`, not that it is a standard ERC-20. For fee-on-transfer, rebasing, or deflationary tokens, the term can believe it holds more collateral than it actually does.
- Impact: If governance onboards a term with a non-standard collateral token, borrowers can be undercollateralized while still passing `maxDebtPerCollateralToken` checks, leading to bad debt and socialized losses for CREDIT/GUILD holders when loans are called or liquidated.

## PSM peg balance tracking is incorrect for non-standard peg tokens
- Location: `src/loan/SimplePSM.sol` : `mint`, `redeem`
- Mechanism: `pegTokenBalance` is updated by nominal `amountIn` / `amountOut` while actual token movements may differ for fee-on-transfer or deflationary peg tokens. The contract assumes `pegToken.balanceOf(this) >= pegTokenBalance`, but redemptions can drain more than accounted or leave the invariant inconsistent.
- Impact: Users may be unable to redeem CREDIT at the expected rate, or an attacker can extract excess peg tokens from the PSM, breaking the CREDIT peg and `totalBorrowedCredit()` accounting that depends on `redeemableCredit()`.

