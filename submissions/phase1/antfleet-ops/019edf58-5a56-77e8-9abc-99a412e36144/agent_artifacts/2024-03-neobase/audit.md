# Audit: 2024-03-neobase

# Audit Findings

## 1. `remove_gauge` zeroes `gauge_types_` before `_remove_gauge_weight` reads it
- Location: `GaugeController.sol` : `remove_gauge` / `_remove_gauge_weight`
- Mechanism: `remove_gauge` sets `gauge_types_[_gauge] = 0` on line one, then calls `_remove_gauge_weight(_gauge)`. Inside `_remove_gauge_weight`, the first line computes `int128 gauge_type = gauge_types_[_gauge] - 1`, which now evaluates to `0 - 1 = -1` (int128 underflow). All subsequent state writes—`points_sum[gauge_type][next_time]`, `points_sum[gauge_type][next_time].slope`, and `changes_sum[gauge_type][time_to_check]`—target gauge type `-1` instead of the real gauge type. The gauge's weight is never subtracted from the correct type sum, and the slope changes are never cancelled from the correct type's `changes_sum`.
- Impact: Removing a gauge does not actually remove its weight from the type sum or cancel its scheduled slope changes. The total weight remains inflated, causing all other gauges to receive a smaller share of inflation/rewards than they should. The orphaned slope changes also cause the type sum to decay incorrectly over time, further distorting reward distribution.

## 2. Users cannot withdraw voting power from removed gauges
- Location: `GaugeController.sol` : `vote_for_gauge_weights`
- Mechanism: The first check `require(_user_weight == 0 || gauge_types_[_gauge_addr] != 0, ...)` is explicitly intended to allow users to vote `0` on a removed (invalid) gauge to withdraw their voting power. However, several lines later the code unconditionally computes `int128 gauge_type = gauge_types_[_gauge_addr] - 1` and requires `gauge_type >= 0`. When the gauge has been removed (`gauge_types_` = 0), `gauge_type` becomes `-1` and the `require` reverts. The first check is dead code for this path.
- Impact: Any user who has voted on a gauge that is later removed by governance is permanently unable to withdraw that vote. Their `vote_user_power` remains non-zero, consuming part of their 10,000 bps voting-power budget. Governance can effectively grief users' voting power by removing gauges they have voted on.

## 3. `update_market` uses current block number instead of the loop variable for epoch timestamp
- Location: `LendingLedger.sol` : `update_market`
- Mechanism: Inside the `while (i < block.number)` loop, `epochTime` is computed as `referenceBlockTime + ((block.number - referenceBlockNumber) * averageBlockTime) / 1000`, using `block.number` (the current block) instead of `i` (the block being processed in that iteration). This means `gaugeController.gauge_relative_weight_write(_market, epochTime)` is called with the *same* (current) timestamp in every iteration, so every epoch's reward is calculated using the gauge's *current* relative weight rather than the weight at that epoch's time.
- Impact: If a gauge's relative weight changed between epochs, past epochs receive the wrong amount of rewards. Epochs where the gauge had a higher weight are under-rewarded, and epochs where it had a lower weight are over-rewarded, leading to systematic mis-distribution of CANTO inflation to lenders.

## 4. `_remove_gauge_weight` does not update `points_total`
- Location: `GaugeController.sol` : `_remove_gauge_weight`
- Mechanism: `_remove_gauge_weight` updates `points_sum[gauge_type][next_time].bias` and `.slope` and cancels `changes_sum` entries, but it never calls `_get_total()` or writes to `points_total`. The total weight still includes the removed gauge's contribution until some other code path (e.g. a subsequent `vote_for_gauge_weights` or `checkpoint`) triggers `_get_total`. `remove_gauge` itself does not call `_get_total` either.
- Impact: Between the gauge removal and the next arbitrary checkpoint, `gauge_relative_weight` returns incorrect (inflated-total) values for all gauges, causing reward distribution to be wrong during that window.

## 5. Unbounded `while` loop in `update_market` can permanently brick a market
- Location: `LendingLedger.sol` : `update_market`
- Mechanism: `update_market` iterates `while (i < block.number)` in steps of at most `BLOCK_EPOCH` (100,000 blocks). If `market.lastRewardBlock` is far behind `block.number` (e.g., the market was not updated for several epochs), the loop runs many iterations, each calling `gaugeController.gauge_relative_weight_write` (an expensive state-mutating function). The total gas can exceed the block gas limit.
- Impact: If `update_market` for a given market becomes too expensive to execute in a single transaction, no user can call `sync_ledger` or `claim` for that market (both call `update_market` internally). The market's rewards become permanently stuck and unreachable. Any user or governance accident that causes a long gap between updates can trigger this.
