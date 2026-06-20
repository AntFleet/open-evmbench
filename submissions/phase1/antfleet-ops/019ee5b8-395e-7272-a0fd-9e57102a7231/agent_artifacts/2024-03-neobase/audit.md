# Audit: 2024-03-neobase

## Historical rewards use the current gauge weight
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: Inside the historical reward loop, `epochTime` is computed from the current `block.number`, not from the loop cursor `i` or the epoch being processed. Every unprocessed historical block range therefore calls `gaugeController.gauge_relative_weight_write(_market, epochTime)` with the same “now” timestamp.
- Impact: A user can wait until their market has favorable gauge weight, then trigger `update_market`; all unprocessed past rewards are retroactively distributed using the current weight instead of the historical weights, misallocating CANTO rewards.

## Reward accumulators can be corrupted at low market supply
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: `accCantoPerShare` and `secRewardsPerShare` are `uint128`, but their increments are computed as `uint256` and narrowed with `uint128(...)`. Solidity narrowing truncates. With dust `marketSupply`, `(blockDelta * rewards * weight) / marketSupply` or `(blockDelta * 1e36) / marketSupply` can exceed `uint128.max`, corrupting the accumulator or causing later checked `uint128` additions to revert.
- Impact: An attacker can seed a whitelisted market with tiny supply, let rewards accrue, and trigger accounting corruption or a market-level DoS for future claims/syncs.

## Gauge removal reads the gauge type after deleting it
- Location: `src/GaugeController.sol` : `remove_gauge`, `_remove_gauge_weight`
- Mechanism: `remove_gauge` sets `gauge_types_[_gauge] = 0` before calling `_remove_gauge_weight`. `_remove_gauge_weight` then computes `gauge_type = gauge_types_[_gauge] - 1`, producing `-1` instead of the real type. For an active gauge, `_get_sum(-1)` is zero and `old_sum_bias - old_weight_bias` underflows.
- Impact: Any gauge with active weight cannot be removed through the intended governance path. A user can keep or add a positive vote before removal and cause removal to revert, preventing governance from disabling a malicious or deprecated gauge.

## Removed gauges trap user voting power
- Location: `src/GaugeController.sol` : `vote_for_gauge_weights`
- Mechanism: The function appears to allow zero-weight votes on removed gauges via `require(_user_weight == 0 || gauge_types_[_gauge_addr] != 0, ...)`, but then unconditionally computes `gauge_type = gauge_types_[_gauge_addr] - 1` and requires `gauge_type >= 0`. For a removed gauge, this always reverts even when `_user_weight == 0`.
- Impact: Users who voted for a gauge before removal cannot clear that vote afterward. Their `vote_user_power` remains consumed, preventing them from reallocating voting power to active gauges.

