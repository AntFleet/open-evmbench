# Audit: 2024-01-canto

I reviewed the three contracts and their interaction. Below are the genuine security/accounting flaws I found.

## GaugeController is queried with a block number where it expects a timestamp
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: The reward loop computes `epoch = (i / BLOCK_EPOCH) * BLOCK_EPOCH`, which is a *block number* aligned to `BLOCK_EPOCH = 100_000`. It then calls `gaugeController.gauge_relative_weight_write(_market, epoch)`. But `GaugeController` works entirely in *timestamps*: `_gauge_relative_weight` floors its `_time` argument with `(_time / WEEK) * WEEK` where `WEEK = 604800` seconds, and weights are recorded at real future timestamps (`next_time = ((block.timestamp + WEEK)/WEEK)*WEEK`). A block number floored to a 604800-second "week" never coincides with any timestamp at which a weight was actually stored (e.g. block 100000 → 0, block 1209600 → a 1970 timestamp), so `points_sum[t].bias` is 0 and the relative weight returned is 0 for essentially every epoch.
- Impact: `cantoReward` is computed as `... * 0 / 1e18 = 0`, so accrued CANTO per share is always (or almost always) zero. The entire gauge-weighted reward distribution is non-functional — CANTO sent to the ledger for incentives is never distributed and the gauge vote outcome has no effect on payouts. This is a core accounting/integration error that breaks the protocol's reward invariant.

## Silent uint128 truncation when updating accumulators
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: `market.accCantoPerShare += uint128((cantoReward * 1e18) / marketSupply);` (and the analogous `secRewardsPerShare` line) explicitly casts a uint256 to `uint128`. When `marketSupply` (`lendingMarketTotalBalance`) is small relative to the reward (e.g. an early/sole depositor holding a few wei while `cantoPerBlock` is non-trivial), `(cantoReward * 1e18) / marketSupply` can exceed `type(uint128).max` (~3.4e38). The cast wraps/truncates rather than reverting, silently corrupting the accumulator.
- Impact: The per-share accumulator can be set to a wrong (much smaller) value, permanently desynchronizing reward accounting for the market. Depending on the truncation an attacker who controls the market supply at the moment of accrual can either zero out legitimate rewards for others or, combined with later `sync_ledger`/`claim` calls, derive `cantoToSend` values inconsistent with the CANTO actually owed.

## De-whitelisting a market permanently strands already-accrued rewards (and can block sync)
- Location: `src/LendingLedger.sol` : `claim` / `sync_ledger` (via `update_market`)
- Mechanism: `update_market` begins with `require(lendingMarketWhitelist[_market], "Market not whitelisted")`, and both `claim` and `sync_ledger` call `update_market` unconditionally. `whiteListLendingMarket(_market, false)` can flip a market off after users have already accrued `rewardDebt`/`accCantoPerShare`. There is no alternate path to claim that bypasses the whitelist check.
- Impact: Once governance de-whitelists a market, every `claim` for that market reverts, so users' already-earned CANTO becomes permanently unclaimable. The same revert also makes `sync_ledger` (called by the lending market on deposit/withdraw) fail; if the lending market does not tolerate that revert, user deposit/withdraw operations against that market are bricked. A single governance toggle (or a market temporarily removed and re-added) results in lost user funds/rewards.

## Missing vote cooldown enables gauge-weight manipulation
- Location: `src/GaugeController.sol` : `vote_for_gauge_weights`
- Mechanism: The function records `last_user_vote[msg.sender][_gauge_addr] = block.timestamp;` but this value is never read anywhere in the contract. The original Curve design gates re-voting with `require(block.timestamp >= last_user_vote + WEIGHT_VOTE_DELAY)` (a ~10-day delay); that check was dropped in this port while the bookkeeping variable was kept. As a result a voter can change their gauge allocation arbitrarily often within the same epoch.
- Impact: A large veCANTO holder can leave weight allocated elsewhere and then flip their full voting power onto a target gauge immediately before the weight is read/snapshotted for reward purposes, then move it back — manipulating gauge relative weight (and thus CANTO reward direction) with no time-locking cost. This defeats the intended Schelling-point/anti-flashloan-style protection of the vote-delay.

## Secondary-reward accounting is maintained but has no claim path
- Location: `src/LendingLedger.sol` : `sync_ledger` / `claim`
- Mechanism: `sync_ledger` continuously maintains `user.secRewardDebt` and `update_market` accrues `secRewardsPerShare`, but `claim` only ever pays out the primary `accCantoPerShare`-based amount. No function reads `secRewardDebt` or `secRewardsPerShare` to disburse the secondary rewards.
- Impact: Any value/accounting represented by the secondary-reward stream is permanently inaccessible to users — the secondary entitlement that the contract computes for every deposit/withdraw can never be redeemed. (Lower severity: depends on whether secondary rewards are ever funded, but the accounting is dead-ended as written.)

Note on the delegation surface in `VotingEscrow`: the `DELEGATE`/`UNDELEGATE` enum values and the `delegatee != msg.sender` branch of `increaseAmount` have no reachable entry point (no public delegate/undelegate function is present), so the lock is always self-delegated and those branches are effectively dead code rather than an exploitable path in this snapshot.

