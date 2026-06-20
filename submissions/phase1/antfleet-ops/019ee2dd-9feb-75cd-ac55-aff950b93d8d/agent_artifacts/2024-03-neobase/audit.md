# Audit: 2024-03-neobase

 ## Governance cannot remove a gauge after adding it
- Location: src/GaugeController.sol : `remove_gauge`
- Mechanism: `remove_gauge` sets `gauge_types_[_gauge] = 0` and then calls `_remove_gauge_weight`. `_remove_gauge_weight` derives the gauge type as `gauge_types_[_gauge] - 1`, which becomes `-1` for a removed gauge. That makes `_get_sum(-1)` return `0`, so the subsequent `old_sum_bias - old_weight_bias` underflows for any gauge that has accrued non-zero weight; even for a zero-weight gauge it mutates the bogus `points_sum[-1]` storage instead of the real type. The order must be reversed (remove weight, then clear type).
- Impact: An active or malicious gauge can never be removed by governance. Compromised/griefing gauges remain in the controller forever and continue to influence reward weights.

## Delisting a lending market bricks all pending claims
- Location: src/LendingLedger.sol : `claim` / `update_market`
- Mechanism: `claim` begins with `update_market(_market)`, which immediately reverts if `lendingMarketWhitelist[_market]` is false. There is no alternative claim path for prior epochs. Because whitelisting is controlled by governance, flipping a market’s whitelist flag to `false` makes every `claim` call for that market revert.
- Impact: Governance (whether compromised or making a configuration error) can permanently freeze all unclaimed CANTO rewards for every user of a market.

## Reward share accumulators silently overflow due to uint128 casts
- Location: src/LendingLedger.sol : `update_market`
- Mechanism: The function accumulates reward shares with:
  ```solidity
  market.accCantoPerShare += uint128(...);
  market.secRewardsPerShare += uint128(...);
  ```
  The per-epoch `uint256` value is cast to `uint128` before the addition. When the true per-epoch increment is larger than `type(uint128).max` (e.g., `secRewardsPerShare` can exceed `2^128 - 1` in a single epoch with small `marketSupply`; `accCantoPerShare` can exceed it after enough epochs), the high bits are silently discarded. Once the real accumulator exceeds `2^128 - 1`, the checked `uint128` addition itself overflows and reverts.
- Impact: Users receive incorrect reward shares (typically underpaid) and, after enough accrual, the market becomes unusable because `update_market`, `sync_ledger`, and `claim` all revert.

## Historic reward epochs use the current week’s gauge weight
- Location: src/LendingLedger.sol : `update_market`
- Mechanism: Inside the per-epoch while-loop, `epochTime` is computed once as `referenceBlockTime + ((block.number - referenceBlockNumber) * averageBlockTime) / 1000` using the current `block.number`. The same timestamp is passed to `gaugeController.gauge_relative_weight_write(_market, epochTime)` for every missed epoch from `lastRewardBlock` up to the present, instead of each block-epoch using its own historical timestamp and historical gauge weight.
- Impact: Reward allocation across missed epochs is weighted by the current-week gauge relative weight rather than the weights that actually applied in those epochs, causing users to be over- or under-paid depending on how weights drifted.

## Gauge weight removal does not update the total weight
- Location: src/GaugeController.sol : `_remove_gauge_weight` / `remove_gauge_weight`
- Mechanism: `_remove_gauge_weight` zeroes `points_weight`, subtracts the old bias/slope from `points_sum`, and cancels future slope changes, but it never recomputes or writes `points_total`. The historical total at `next_time` therefore still contains the gauge’s old contribution.
- Impact: Until the global total is checkpointed again through unrelated activity, `gauge_relative_weight` reads a stale `points_total[t]` that dilutes the relative weights of the remaining gauges, causing incorrect reward shares for all markets.

## `change_gauge_weight` accepts unregistered gauges and corrupts state
- Location: src/GaugeController.sol : `change_gauge_weight` / `_change_gauge_weight`
- Mechanism: The function has no `require(gauge_types_[addr] != 0)`. For an unregistered gauge, `int128 gauge_type = gauge_types_[addr] - 1` evaluates to `-1`, so the function reads and writes `points_sum[-1]`, `time_sum[-1]`, and `points_type_weight[-1]` — storage slots associated with an invalid type ID.
- Impact: A compromised or mistaken governance call can corrupt the controller’s accounting arrays and total-weight calculations for a non-existent gauge type.

## Governance transfer is single-step and unvalidated
- Location: src/GaugeController.sol : `setGovernance`; src/LendingLedger.sol : `setGovernance`; src/VotingEscrow.sol : `setGovernance`
- Mechanism: Each `setGovernance` immediately overwrites `governance` with the supplied address. There is no zero-address check and no pending-acceptance / two-step pattern. A typo or a governance-key compromise therefore sets an unrecoverable governance address.
- Impact: All `onlyGovernance` functions can be permanently bricked, or control can be irrevocably transferred to an attacker-controlled address.
