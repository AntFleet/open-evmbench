# Audit: 2023-12-ethereumcreditguild
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

Before emitting, here is my finding census.

**Report population:** 6 reports total (claude-opus-4-8 shots 1–3, gpt-5.5 shots 1–3), so M = 6. The three claude-opus-4-8 shots produced no analysis (truncated/non-substantive output: "me ultrathink", a bare preamble, and "targetTimestamp; uint224 targetValue."). They therefore contribute no findings and, critically, **defend no code path** — so there are no *conflicting reviews* annotations to add. All substantive findings come from the three gpt-5.5 shots.

**Distinct findings counted in inputs:** 10 (A–J below). **Findings in output:** 10. No drops.

---

## Consensus findings

## New/late gauge voters can claim historical gauge profit rewards
*(consensus, 3 of 6 reports)*
- Location: `src/governance/ProfitManager.sol` : `claimGaugeRewards`; `src/tokens/GuildToken.sol` : `_incrementGaugeWeight`
- Mechanism: `claimGaugeRewards` returns immediately when the user's current gauge weight is zero, without initializing `userGaugeProfitIndex[user][gauge]` to the current `gaugeProfitIndex`. `GuildToken._incrementGaugeWeight` calls `claimGaugeRewards` before adding the new weight, so a first-time/returning voter keeps a zero (or stale `1e18`) profit index and is later treated as if they had been voting since the gauge index started.
- Impact: An attacker waits until a gauge has accrued CREDIT rewards, allocates GUILD weight afterward, then claims a pro-rata share of historical rewards they did not earn — stealing CREDIT from earlier voters and potentially draining the ProfitManager's CREDIT balance (including surplus/loss-accounting funds) or causing later legitimate claims to revert.

## Post-loss SurplusGuildMinter stakes are incorrectly slashed
*(consensus, 3 of 6 reports)*
- Location: `src/loan/SurplusGuildMinter.sol` : `getRewards`
- Mechanism: `getRewards` evaluates `lastGaugeLoss > uint256(userStake.lastGaugeLoss)` before executing `userStake = _stakes[user][term]`, so the comparison reads the default-zero `lastGaugeLoss` from the still-uninitialized memory struct. After any historical loss on a term (nonzero `lastGaugeLoss`), every user is flagged `slashed`, including those who staked after the loss and recorded the correct timestamp.
- Impact: Once a term has ever had a loss, anyone can call `getRewards(victim, term)` (or reach it via `unstake`/`updateMintRatio`) and wipe a valid later stake. The victim forfeits the CREDIT they contributed to the term surplus buffer and their rewards, and the minted GUILD gauge weight can become orphaned/stranded in the minter contract.

## First rebasing account can manipulate the CREDIT rebase share price
*(consensus, 3 of 6 reports)*
- Location: `src/tokens/ERC20RebaseDistributor.sol` : `_enterRebase`/`enterRebase`, `distribute` (also cited with `_exitRebase` / `updateTotalRebasingShares`)
- Mechanism: The rebasing share system enforces no minimum seed liquidity or minimum shares. While `totalRebasingShares` is tiny, the first account can enter rebasing with dust and then `distribute`, setting a very large share price against that minimal share base. Later entrants receive few or zero shares because `_balance2shares` rounds down.
- Impact: If CREDIT rebasing is not pre-seeded with a meaningful permanent balance, the first rebasing holder can capture a disproportionate share of early/future CREDIT distributions, while smaller later participants are rounded down to little or no rewards — making rebasing economically distorted or unusable for them.

## Full bad-debt loss can zero or brick the credit multiplier / loss realization
*(consensus, 2 of 6 reports)*
- Location: `src/governance/ProfitManager.sol` : `notifyPnL`
- Mechanism: In the loss path, when losses exceed the surplus buffer, the new multiplier is computed as `(creditMultiplier * (creditTotalSupply - loss)) / creditTotalSupply` with no handling for `loss >= creditTotalSupply`. If `loss == creditTotalSupply`, `creditMultiplier` becomes zero; if `loss > creditTotalSupply`, the subtraction underflows and reverts.
- Impact: A sufficiently large bad-debt event can make auction settlement/forgiveness revert (loans and auctions stuck and the loss never accounted), or drive `creditMultiplier` to zero and permanently brick later PSM/borrow/`minBorrow` math that divides by it. Preconditions are severe but plausible in insolvency — e.g., after borrowed CREDIT has been redeemed and burned through the PSM, shrinking total supply.

## Rebasing self-transfer corrupts share accounting (inflates balances/voting power)
*(consensus, 2 of 6 reports)*
- Location: `src/tokens/ERC20RebaseDistributor.sol` : `transfer`, `transferFrom`
- Mechanism: For rebasing accounts the sender and recipient branches are processed independently against the pre-transfer state. When `from == to`, the sender branch reduces shares, then the recipient branch reloads the pre-transfer state and overwrites the same storage slot with increased shares; `sharesDelta` nets ~zero, so `totalRebasingShares` is not increased to match the account's inflated final `nShares`.
- Impact: A rebasing CREDIT holder can self-transfer to inflate apparent `balanceOf()` and then delegate inflated voting power via `ERC20MultiVotes`. With sufficient pending (unminted) rewards they can materialize more than their fair share and drain rewards from other rebasing holders; without enough pending rewards the same corruption can underflow and brick the account's later transfers/exits.

## Re-onboarded terms can be offboarded again without a fresh vote
*(consensus, 2 of 6 reports)*
- Location: `src/governance/LendingTermOffboarding.sol` : `offboard`, `cleanup`; `src/governance/LendingTermOnboarding.sol` : `proposeOnboard`
- Mechanism: `offboard` leaves `canOffboard[term]` set true (and does not record that the term is already in an offboarding flow) until `cleanup` runs. `proposeOnboard` only checks that the term is not currently an active gauge, so a deprecated term can be re-onboarded before cleanup while the stale `canOffboard` authorization persists.
- Impact: A single previously-passed offboarding quorum can be reused to repeatedly remove a re-onboarded term with no new poll, and each reuse increments `nOffboardingsInProgress` again for the same term. This desynchronizes the counter so that, after the eventual single cleanup, it can remain nonzero and keep PSM redemptions paused indefinitely.

---

## Minority findings

## Rate-limited minters can refill their own mint buffer
*(minority, 1 of 6 reports)*
- Location: `src/rate-limits/RateLimitedMinter.sol` : `replenishBuffer`
- Mechanism: `replenishBuffer` is callable by the same `role` that is permitted to mint and accepts an arbitrary `amount` without proving that any tokens were actually burned, letting a holder of the rate-limited role restore minting capacity at will.
- Impact: A compromised, malicious, or mistakenly granted rate-limited minter can bypass the rate limit by alternating `replenishBuffer` and `mint`, escalating from rate-limited minting to effectively unbounded minting up to token-level permissions.

## Fee-on-transfer collateral is over-credited
*(minority, 1 of 6 reports)*
- Location: `src/loan/LendingTerm.sol` : `_borrow`, `_addCollateral`, `_repay`, `onBid`
- Mechanism: The term records the requested `collateralAmount` rather than measuring the actual token balance delta received, so a fee-on-transfer or rebasing collateral token leaves the contract holding less collateral than it records while borrow limits and later collateral returns use the inflated recorded amount.
- Impact: On any onboarded term using such a token, a borrower can be undercollateralized immediately, withdraw more collateral than was deposited, steal collateral from other loans sharing the same token balance, or cause repayment/liquidation paths to fail. Precondition: a fee-on-transfer/balance-changing collateral token is onboarded.

## Fee-on-transfer peg token makes the PSM insolvent
*(minority, 1 of 6 reports)*
- Location: `src/loan/SimplePSM.sol` : `mint`, `mintAndEnterRebase`, `redeem`
- Mechanism: `pegTokenBalance` is increased by the nominal `amountIn` and CREDIT is minted from that nominal amount, with no measurement of how many peg tokens were actually received; with a fee-on-transfer or rebasing peg token, accounted liabilities exceed real assets.
- Impact: An attacker can mint CREDIT against gross peg-token input while the PSM actually receives less, then redeem (or leave other users unable to redeem fully), rendering the PSM insolvent. Precondition: the PSM is deployed with a fee-on-transfer/balance-changing peg token.

## Gauge loss slashing can be blocked by debt-ceiling checks
*(minority, 1 of 6 reports)*
- Location: `src/tokens/GuildToken.sol` : `applyGaugeLoss`, `_decrementGaugeWeight`
- Mechanism: `applyGaugeLoss` routes through the overridden `_decrementGaugeWeight`, which still enforces the normal "debt ceiling used" guard via `LendingTerm(gauge).debtCeiling(-int256(weight))`. The loss-burn path can therefore revert whenever outstanding issuance would exceed the reduced debt ceiling.
- Impact: Voters backing a lossy lending term may be impossible to slash while the term still has enough active issuance, so their GUILD supply and delegated governance voting power remain live instead of being burned, and the gauge's weight stays inflated after a reported loss.

