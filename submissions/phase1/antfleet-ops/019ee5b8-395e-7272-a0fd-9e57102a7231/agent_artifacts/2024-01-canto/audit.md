# Audit: 2024-01-canto

## Removed-gauge vote clearing corrupts total gauge weight
- Location: `src/GaugeController.sol` : `_remove_gauge_weight` / `vote_for_gauge_weights`
- Mechanism: `_remove_gauge_weight` already subtracts the removed gauge’s aggregate bias and slope from `points_sum`, but it leaves each user’s `vote_user_slopes` entry intact. A former voter can later call `vote_for_gauge_weights(removedGauge, 0)`, which treats the old vote as still present in the global sum and subtracts `old_bias` / `old_slope` from `points_sum` again.
- Impact: A former voter of a removed gauge can corrupt global gauge totals. Remaining gauges can receive relative weights above `1e18`, allowing excess CANTO distribution, or totals can be driven to zero / inconsistent values, breaking reward accounting.

## Lending rewards use block numbers as gauge timestamps
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: `epoch` is computed from `block.number`, then passed to `gaugeController.gauge_relative_weight_write(_market, epoch)`. The gauge controller expects `_time` to be a Unix timestamp and floors it by `WEEK`. On a real chain, block-number epochs point to unrelated or uninitialized timestamp buckets, so gauge weights are read from the wrong time.
- Impact: Anyone can call `update_market` for a whitelisted market and advance `lastRewardBlock` while accounting elapsed blocks with zero or wrong gauge weight. Users can be denied earned CANTO rewards, and emissions can become stuck/unallocated.

## Reward epoch boundaries are calculated from the last update block
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: The loop sets `nextEpoch = i + BLOCK_EPOCH` instead of the next canonical boundary, `epoch + BLOCK_EPOCH`. If `lastRewardBlock` is not exactly epoch-aligned, one epoch’s `cantoPerBlock` and gauge weight are applied across the next epoch boundary.
- Impact: Because `update_market` is public, an attacker can time updates around reward changes to extend a favorable old epoch rate into a new epoch and over-accrue rewards, or extend an unfavorable/zero rate to suppress rewards for other lenders.

