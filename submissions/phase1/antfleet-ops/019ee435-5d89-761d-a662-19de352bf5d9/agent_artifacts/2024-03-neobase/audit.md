# Audit: 2024-03-neobase

## Historical rewards use current gauge weight
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: Inside the loop over past block epochs, `epochTime` is computed from the current `block.number` instead of the loop cursor `i` or the epoch being processed. As a result, every missed reward epoch calls `gaugeController.gauge_relative_weight_write(_market, epochTime)` with the current estimated timestamp, so delayed market updates apply today’s gauge weight to all previously unaccounted blocks.
- Impact: A supplier can leave a market unupdated, later obtain/increase gauge weight, then trigger `update_market` and receive rewards for past epochs as if that gauge weight had existed historically. This misallocates emissions and can drain rewards away from correctly weighted markets.

## Per-share reward accumulators can truncate or brick accounting
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: `accCantoPerShare` and `secRewardsPerShare` are stored as `uint128`, but their increments are scaled by `1e18` and `1e36`. With small `marketSupply` or a delayed update, `(blockDelta * reward * weight) / marketSupply` and `(blockDelta * 1e36) / marketSupply` can exceed `uint128`. The explicit `uint128(...)` cast truncates high bits, and subsequent `uint128` addition can also revert once the accumulator is near the limit.
- Impact: An attacker can deposit a dust amount into a whitelisted/gauge market and wait, causing reward accounting to become corrupted or permanently revert on later deposits, withdrawals, claims, or updates for that market.

## Active gauges cannot be reliably removed
- Location: `src/GaugeController.sol` : `remove_gauge`
- Mechanism: `remove_gauge` sets `gauge_types_[_gauge] = 0` before calling `_remove_gauge_weight`. `_remove_gauge_weight` then derives `gauge_type = gauge_types_[_gauge] - 1`, which becomes `-1` instead of the original type. For gauges with active weight, it reads the wrong type sum and can underflow when computing `old_sum_bias - old_weight_bias`, reverting the removal.
- Impact: Any user with voting power can place a small vote on a gauge and make the normal governance removal path revert. A malicious or compromised gauge can remain active unless governance uses a separate workaround.

## Removed-gauge votes cannot be cleared
- Location: `src/GaugeController.sol` : `vote_for_gauge_weights`
- Mechanism: The function intends to allow `_user_weight == 0` for removed gauges, but after that check it still computes `gauge_type = gauge_types_[_gauge_addr] - 1` and requires `gauge_type >= 0`. Once a gauge is removed and its stored type is zero, even a zero-weight vote reverts.
- Impact: Users who voted for a removed gauge cannot withdraw that vote from `vote_user_power`; their voting power can remain locked until their ve lock expires, preventing reallocation to valid gauges.

