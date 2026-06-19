# Audit: 2024-03-neobase

## Historical rewards are distributed using the current gauge weight
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: Inside the epoch loop, `epochTime` is calculated from `block.number`, not from the loop cursor `i` or `epoch`. As a result, every unprocessed historical block range is priced with the gauge relative weight for the current estimated time. The vulnerable path is `update_market()` → loop over old block epochs → `gaugeController.gauge_relative_weight_write(_market, epochTime)`, where `epochTime` is constant for the whole update and represents “now”.
- Impact: An attacker can wait until their market has a favorable gauge weight, then trigger `update_market` after the market has accumulated unprocessed blocks. Rewards for past epochs are then retroactively assigned using the attacker-favorable current gauge weight, allowing misallocation of CANTO away from the markets that actually had weight during those epochs.

## Reward accumulators can truncate or brick markets at low supply
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: `accCantoPerShare` and `secRewardsPerShare` are `uint128`, but the per-share increments are computed as full `uint256` values and then narrowed with `uint128(...)`. Solidity narrowing casts truncate instead of reverting. With very small `marketSupply`, especially dust supply, expressions like `(blockDelta * 1e36) / marketSupply` or the CANTO reward expression can exceed `uint128.max`. The stored accumulator then becomes corrupted, or later `uint128` addition can revert.
- Impact: An attacker can deposit a dust amount into a whitelisted market, wait for enough blocks, and trigger `update_market` to corrupt reward accounting or make future `claim`, `sync_ledger`, deposits, and withdrawals revert for that market.

## Gauge removal reads the gauge type after deleting it
- Location: `src/GaugeController.sol` : `remove_gauge`, `_remove_gauge_weight`
- Mechanism: `remove_gauge` first sets `gauge_types_[_gauge] = 0`, then calls `_remove_gauge_weight(_gauge)`. `_remove_gauge_weight` derives the type with `gauge_types_[_gauge] - 1`, so it reads `-1` instead of the real gauge type. For an active gauge, `_get_sum(-1)` returns zero and `old_sum_bias - old_weight_bias` underflows, reverting. If the gauge has no weight, the cleanup targets the wrong type bucket.
- Impact: A gauge with active votes cannot be removed through the intended governance removal path. A malicious or broken gauge can remain active until governance discovers and executes a non-obvious workaround.

## Removed gauges can permanently trap user voting power
- Location: `src/GaugeController.sol` : `vote_for_gauge_weights`
- Mechanism: The function appears to allow users to withdraw voting power from removed gauges with `_user_weight == 0` via `require(_user_weight == 0 || gauge_types_[_gauge_addr] != 0, ...)`. However, it immediately computes `gauge_type = gauge_types_[_gauge_addr] - 1` and requires `gauge_type >= 0`, which rejects removed gauges even when the user is trying to vote zero. Their `vote_user_power` is therefore never decremented.
- Impact: After a gauge is removed, users who previously voted for it can be unable to free that voting power and reallocate it elsewhere until their old vote naturally expires. This can lock users out of governance-weight allocation for long periods.

