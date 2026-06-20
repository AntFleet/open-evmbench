# Audit: 2024-03-neobase

## Retroactive gauge-vote snapshot lets a market steal past emissions
- Location: [src/LendingLedger.sol](/Users/augstar/open-evmbench/audit_sources/2024-03-neobase/src/LendingLedger.sol:64) lines 64-89 : `update_market`
- Mechanism: `update_market` iterates over historical block epochs, but `epochTime` is computed once from the current `block.number` (`referenceBlockTime + ((block.number - referenceBlockNumber) * averageBlockTime) / 1000`) instead of from the loop cursor `i`/`epoch`. Every `blockDelta` chunk therefore uses the same present-time gauge weight in `gaugeController.gauge_relative_weight_write(_market, epochTime)`, even for rewards that should have used older weekly votes. A user can keep a dust position in a quiet market, wait for rewards to accrue without updates, move votes to that market shortly before the first `update_market`, and have the whole backlog priced at the new weight.
- Impact: Historical CANTO emissions can be redirected to the market with the latest vote snapshot instead of the markets that actually had weight during those epochs, allowing reward theft from honest markets.

## `uint128` accumulator truncation corrupts reward accounting
- Location: [src/LendingLedger.sol](/Users/augstar/open-evmbench/audit_sources/2024-03-neobase/src/LendingLedger.sol:80) lines 80-85 : `update_market`
- Mechanism: `accCantoPerShare` and `secRewardsPerShare` are `uint128`, but each loop iteration computes an unbounded `uint256` increment and explicitly downcasts it with `uint128(...)`. In Solidity 0.8 this does not revert; it truncates. Because the increment scales as `blockDelta * cantoPerBlock * weight / marketSupply`, an attacker can make `marketSupply` tiny by being the only dust depositor in a fresh market, and a normal governance reward rate can then overflow the 128-bit cast.
- Impact: The per-share accumulator can wrap to an arbitrary lower value, causing users to be underpaid, overpaid, or unable to claim because the contract’s stored accounting no longer matches the intended rewards.

## Removing a gauge can permanently lock users’ voting power
- Location: [src/GaugeController.sol](/Users/augstar/open-evmbench/audit_sources/2024-03-neobase/src/GaugeController.sol:224) lines 224-228 and [src/GaugeController.sol](/Users/augstar/open-evmbench/audit_sources/2024-03-neobase/src/GaugeController.sol:385) lines 385-402 : `remove_gauge`, `vote_for_gauge_weights`
- Mechanism: The function comments say users may vote `0` on removed gauges to withdraw voting power, but that path is unreachable. After `remove_gauge` sets `gauge_types_[_gauge] = 0`, `vote_for_gauge_weights` still executes `int128 gauge_type = gauge_types_[_gauge_addr] - 1; require(gauge_type >= 0, "Gauge not added");`, so every zero-weight withdrawal on a removed gauge reverts. Separately, `remove_gauge` zeroes `gauge_types_` before `_remove_gauge_weight`, so governance cannot even remove a weighted gauge in one call without first using the separate weight-removal workaround.
- Impact: Any user who voted for a removed gauge can have some or all of `vote_user_power` stuck until lock expiry, preventing them from reallocating votes and allowing targeted censorship of voters through gauge removal.

## `remove_gauge_weight` followed by a user revote double-subtracts global weight
- Location: [src/GaugeController.sol](/Users/augstar/open-evmbench/audit_sources/2024-03-neobase/src/GaugeController.sol:350) lines 350-372 and [src/GaugeController.sol](/Users/augstar/open-evmbench/audit_sources/2024-03-neobase/src/GaugeController.sol:425) lines 425-459 : `_remove_gauge_weight`, `vote_for_gauge_weights`
- Mechanism: `_remove_gauge_weight` already removes the gauge’s bias/slope from `points_sum[gauge_type][next_time]` and clears its future `changes_sum`. If a voter later calls `vote_for_gauge_weights` on that still-valid gauge, the function assumes the old vote is still included in `old_sum_bias` / `old_sum_slope` and subtracts `old_bias` / `old_slope` again via `Math.max(...)-old_*`. Once governance has manually zeroed the gauge, that assumption is false, so the type-wide totals are reduced a second time.
- Impact: Relative-weight accounting for every other gauge in the same type becomes too low or even zero, skewing or halting emissions for unrelated markets.

## Unbounded catch-up loop can permanently DoS claims and ledger updates
- Location: [src/LendingLedger.sol](/Users/augstar/open-evmbench/audit_sources/2024-03-neobase/src/LendingLedger.sol:64) lines 64-89 : `update_market`
- Mechanism: `update_market` walks from `lastRewardBlock` to `block.number` one `BLOCK_EPOCH` at a time with no cap and no partial checkpointing. If a market is left untouched long enough, the loop grows until it cannot fit in the block gas limit. Because `sync_ledger` and `claim` both call `update_market` before they can change state, no caller can advance `lastRewardBlock` once that threshold is crossed.
- Impact: A sufficiently stale market can become permanently unserviceable: reward claims fail, and any deposit/withdraw flow that depends on `sync_ledger` is bricked for that market.

