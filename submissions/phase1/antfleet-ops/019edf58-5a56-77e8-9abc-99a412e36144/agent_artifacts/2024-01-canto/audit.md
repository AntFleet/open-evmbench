# Audit: 2024-01-canto

## Block numbers passed as timestamps to GaugeController
- Location: src/LendingLedger.sol : update_market
- Mechanism: `update_market` computes `epoch = (i / BLOCK_EPOCH) * BLOCK_EPOCH`, which is a **block number**, then passes it to `gaugeController.gauge_relative_weight_write(_market, epoch)`. Inside `GaugeController._gauge_relative_weight`, the value is treated as a timestamp and floored to a week: `uint256 t = (_time / WEEK) * WEEK` where `WEEK = 7 days`. The `points_sum` and `points_weight` mappings are keyed by actual weekly Unix timestamps (e.g. ~1.7e9), not block numbers (e.g. 100 000). The floored block number never matches any real weekly timestamp, so `total_weight` and `gauge_weight` are always read as 0.
- Impact: `gauge_relative_weight_write` always returns 0, so `cantoReward` is always 0. No CANTO rewards are ever accrued or distributed to any lending market, completely breaking the incentive system.

## Epoch-boundary misalignment in reward accumulation
- Location: src/LendingLedger.sol : update_market
- Mechanism: When computing the next epoch boundary the code uses `nextEpoch = i + BLOCK_EPOCH` instead of `nextEpoch = epoch + BLOCK_EPOCH`. Because `lastRewardBlock` is set to `block.number` at whitelisting (which is almost never on a `BLOCK_EPOCH` boundary), `i` starts mid-epoch. The loop then applies the previous epoch's `cantoPerBlock` rate for `BLOCK_EPOCH` blocks starting from the mid-epoch position, crossing into the next epoch's range, and subsequently shifts every subsequent epoch's reward window by the initial offset.
- Impact: Rewards for every epoch after the market is whitelisted are calculated with the wrong `cantoPerBlock` rate for a portion of blocks, causing systematic over- or under-distribution of CANTO relative to governance's intended schedule.

## Withdrawing votes from a removed gauge corrupts the global sum accounting
- Location: src/GaugeController.sol : vote_for_gauge_weights
- Mechanism: When governance calls `remove_gauge` / `_remove_gauge_weight`, the gauge's entire slope and bias are already subtracted from `points_sum[next_time]` and all future `changes_sum` entries for that gauge are zeroed. A user who had an active vote on that gauge must later call `vote_for_gauge_weights(_gauge, 0)` to reclaim their `vote_user_power`. In that call the code executes `points_sum[next_time].bias = Math.max(old_sum_bias + new_bias, old_bias) - old_bias` and (when `old_slope.end > next_time`) `points_sum[next_time].slope = Math.max(old_sum_slope + new_slope.slope, old_slope.slope) - old_slope.slope` with `new_bias = 0` and `new_slope.slope = 0`. Because `old_sum_bias` / `old_sum_slope` no longer contain the user's contribution (it was already removed by `_remove_gauge_weight`), the `Math.max(...) - old_*` expression subtracts the user's old contribution a second time from the global sum (or forces it to zero).
- Impact: The global total weight's slope and bias are incorrectly reduced, corrupting the relative-weight calculation for **all remaining valid gauges**. This can permanently skew emission distribution after any gauge removal that had active votes.
