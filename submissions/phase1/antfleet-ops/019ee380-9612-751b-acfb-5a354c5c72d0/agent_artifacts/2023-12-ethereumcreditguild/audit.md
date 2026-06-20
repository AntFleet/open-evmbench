# Audit: 2023-12-ethereumcreditguild

# Security Audit — Ethereum Credit Guild

Below are the genuine vulnerabilities I found, ordered by severity.

## `canOffboard` is never cleared on offboard, allowing permissionless re-offboarding and PSM redemption DoS
- Location: `src/governance/LendingTermOffboarding.sol` : `offboard` / `cleanup` (and `supportOffboard`)
- Mechanism: `canOffboard[term]` is set to `true` in `supportOffboard` once a poll reaches quorum, and is only ever set back to `false` inside `cleanup`. `offboard()` itself does **not** reset it. `cleanup()` additionally requires the term to be a *deprecated* gauge (`isDeprecatedGauge`) and to have `issuance() == 0`. Re-onboarding a previously offboarded term is an explicitly supported feature (`LendingTermOnboarding.proposeOnboard` allows re-onboarding). Therefore, after a term is offboarded, if it is re-onboarded before `cleanup` runs (or if `cleanup` simply hasn't been called yet), `canOffboard[term]` remains permanently `true` while the term is live again. Any account can then call `offboard(term)` at will — with no fresh poll and no quorum — because the only gate is `require(canOffboard[term])`. This both bypasses the governance quorum and, via `nOffboardingsInProgress++`, pauses `SimplePSM` redemptions.
- Impact: An attacker who benefited from one historical passed poll can repeatedly remove a live, healthy lending term from the gauge system and pause all PSM redemptions on demand, with zero stake and no new vote. The increment/decrement of `nOffboardingsInProgress` also desyncs: each spurious `offboard` increments the counter while only a matching `cleanup` (which may now be impossible because the term is live/non-deprecated) decrements it, so the counter can be driven permanently `> 0`, leaving `SimplePSM` redemptions paused indefinitely (protocol-wide denial of service on the peg).

## Forgiving a called loan bricks its in-progress auction and strands collateral
- Location: `src/loan/LendingTerm.sol` : `forgive`
- Mechanism: `LendingTerm.forgive` checks only `borrowTime != 0` and `closeTime == 0`; it does **not** check `callTime == 0`. A loan that has already been called has a live auction in the `AuctionHouse` (`nAuctionsInProgress` incremented, `auctions[loanId].endTime == 0`). When `forgive` is called on such a loan it sets `loans[loanId].closeTime = block.timestamp` and reduces `issuance`. Later, when the auction settles (`AuctionHouse.bid` or `AuctionHouse.forgive` → `LendingTerm.onBid`), `onBid` reverts on `require(loans[loanId].closeTime == 0, "loan closed")`. The auction can therefore never be concluded.
- Impact: `nAuctionsInProgress` is stuck above zero forever for that term, which permanently blocks `setAuctionHouse` (it requires `nAuctionsInProgress() == 0`), and the auctioned collateral can never be released to bidder or borrower through the normal path, requiring a governance `emergencyAction` rescue. Although `forgive` is GOVERNOR-gated, the missing `callTime` guard turns a routine emergency action into an unrecoverable state for that term’s auction lifecycle.

## Per-loan loss can be front-run via PSM redemption (loss-socialization avoidance)
- Location: `src/loan/SimplePSM.sol` : `redeem` (in combination with `ProfitManager.notifyPnL` / `LendingTerm.onBid`)
- Mechanism: When an under-collateralized loan is liquidated, the loss is only realized atomically at bid time (`AuctionHouse.bid` → `LendingTerm.onBid` → `ProfitManager.notifyPnL`), which decrements `creditMultiplier` and thus the per-CREDIT redemption value (`getRedeemAmountOut = amountIn * creditMultiplier / 1e18 / decimalCorrection`). PSM redemptions are only paused for *offboarding* (`LendingTermOffboarding.offboard`), not for ordinary loan-loss liquidations. A CREDIT holder who observes an in-progress auction that is certain to settle below principal can call `SimplePSM.redeem` in an earlier block and exit at the pre-loss `creditMultiplier`, draining peg reserves at full value.
- Impact: The first-loss/seniority model (surplus buffer, then proportional CREDIT discount) is partially defeated: informed holders redeem at the stale multiplier before the loss is booked, concentrating a larger `creditMultiplier` drop onto the remaining, slower holders. This is a value transfer away from passive CREDIT holders toward those who monitor the auction queue.

---

I reviewed the access-control wiring (Core/CoreRef roles, `GuildTimelockController` role redirection, rate-limited minters), the rebase accounting in `ERC20RebaseDistributor`, gauge weight bookkeeping in `ERC20Gauges`/`GuildToken`, and the auction math; aside from the items above I did not find additional exploitable flaws. Note that `GuildToken._decrementGaugeWeight`’s debt-ceiling guard can legitimately freeze a user’s/SGM staker’s ability to unstake while a term is at capacity, but that is a documented, intended constraint rather than a vulnerability.

