# Audit: 2024-03-neobase

# Security Audit Report

Findings below are limited to genuine logic, accounting, and access-control flaws on exploitable or broken code paths.

---

## Historical rewards accrue using current gauge weight, not historical weight

- **Location:** `LendingLedger.sol` : `update_market`
- **Mechanism:** Inside the catch-up loop over `i` (historical blocks), `epochTime` is always derived from the **current** `block.number`, not from `i` or the midpoint of `blockDelta`. Every retroactive slice therefore calls `gaugeController.gauge_relative_weight_write(_market, epochTime)` with the **present** estimated timestamp, while `cantoPerBlock[epoch]` correctly uses the historical block epoch from `i`. After long gaps without `update_market`, all missed emissions are re-priced at today’s vote weights instead of the weights that were active when those blocks were mined.
- **Impact:** A ve-token holder can vote to raise a market’s gauge weight, then trigger `update_market` (via `sync_ledger`, `claim`, etc.) on a stale market and re-attribute past epochs at the inflated weight. That market’s lenders claim excess CANTO from `LendingLedger`, diluting rewards for every other market. This is a direct emission-theft path and does not require governance.

```solidity
uint256 epochTime = referenceBlockTime +
    ((block.number - referenceBlockNumber) * averageBlockTime) / 1000;
// should use block `i` (or i + blockDelta/2), not block.number
```

---

## `remove_gauge` clears gauge type before weight removal, corrupting accounting

- **Location:** `GaugeController.sol` : `remove_gauge` → `_remove_gauge_weight`
- **Mechanism:** `remove_gauge` sets `gauge_types_[_gauge] = 0` **before** calling `_remove_gauge_weight`. `_remove_gauge_weight` then reads `int128 gauge_type = gauge_types_[_gauge] - 1`, which is `-1` instead of the real type. All sum/slope adjustments (`_get_sum`, `points_sum`, `changes_sum`, etc.) are applied to the phantom type `-1`, while the real type’s aggregate weight is never reduced. `remove_gauge_weight()` alone does not have this bug because it does not zero `gauge_types_` first.
- **Impact:** Any governance gauge removal via `remove_gauge` leaves the removed gauge’s weight in the real type total, corrupts the type `-1` slots, and breaks `points_total` / relative-weight math. Emission shares become wrong globally; some markets can be over- or under-rewarded until manual recovery. `_gauge_relative_weight` on a removed address also reads `gauge_types_[_gauge] - 1 == -1`, so whitelisted markets whose gauge was removed get nonsensical weights.

```solidity
function remove_gauge(address _gauge) external onlyGovernance {
    gauge_types_[_gauge] = 0;          // zeroed first
    _remove_gauge_weight(_gauge);      // gauge_type becomes -1 inside
}
```

---

## Votes cannot be withdrawn from removed gauges, permanently locking ve power

- **Location:** `GaugeController.sol` : `vote_for_gauge_weights`
- **Mechanism:** Removed gauges allow `_user_weight == 0` in the first `require`, but the function later does `int128 gauge_type = gauge_types_[_gauge_addr] - 1` and `require(gauge_type >= 0, "Gauge not added")`. For a removed gauge, `gauge_types_` is `0`, so `gauge_type == -1` and the tx reverts. Users cannot call `vote_for_gauge_weights(removedGauge, 0)` to free `vote_user_power` or clear `vote_user_slopes`.
- **Impact:** After `remove_gauge`, voting power allocated to that gauge is stuck forever in `vote_user_power[msg.sender]`, reducing the power available for other gauges (max 10_000 bps). This is a permanent protocol-level griefing / logic failure affecting all voters on removed gauges.

---

## Gauge wrapper credits rewards without capital in the lending market

- **Location:** `LiquidityGauge.sol` : `depositUnderlying` / `_afterTokenTransfer`; `LendingLedger.sol` : `sync_ledger`
- **Mechanism:** `LiquidityGauge.depositUnderlying` pulls underlying into the gauge and mints 1:1 gauge shares; `_afterTokenTransfer` calls `LendingLedger.sync_ledger`, which increases `lendingMarketTotalBalance` and the user’s `userInfo.amount`. No call is made to the lending market’s own deposit/supply path. Rewards in `update_market` are divided by `lendingMarketTotalBalance`, which now includes gauge-held balances that are **not** productive TVL in the lending protocol.
- **Impact:** Anyone with the underlying/cNOTE token can deposit into the gauge, earn CANTO emissions as if they were supplying the market, and withdraw anytime via `withdrawUnderlying`, while capital sits idle in the gauge. This misallocates emissions away from actual lenders and can be scaled to capture a large share of epoch rewards.

---

## `accCantoPerShare` silent overflow via `uint128` cast

- **Location:** `LendingLedger.sol` : `update_market`
- **Mechanism:** The per-share accumulator is stored as `uint128` and updated with an unchecked narrowing cast: `market.accCantoPerShare += uint128((blockDelta * cantoPerBlock[epoch] * weight) / marketSupply)`. If the computed increment or running total exceeds `2^128 - 1`, Solidity truncates silently.
- **Impact:** Once the accumulator wraps, `claim` and `sync_ledger` compute wrong `accumulatedCanto - rewardDebt` values. Users can receive far less than entitled, or—depending on wrap timing—far more, draining `LendingLedger`’s native balance at the expense of others. High `cantoPerBlock`, high gauge weight, or long periods without updates increase risk.

---

## `remove_gauge` does not update `points_total`

- **Location:** `GaugeController.sol` : `_remove_gauge_weight` (called from `remove_gauge`)
- **Mechanism:** `_change_gauge_weight` recomputes and writes `points_total[next_time]` and `time_total`. `_remove_gauge_weight` updates per-gauge and per-type sums but never updates `points_total`. Unlike `vote_for_gauge_weights` and `gauge_relative_weight_write`, `remove_gauge` does not call `_get_total()`.
- **Impact:** After gauge removal, `points_total` stays stale until someone externally checkpoints. `gauge_relative_weight` (view) and any consumer that reads weights before a write-path checkpoint uses a wrong denominator, causing incorrect relative weights and misallocated CANTO until corrected.

---

## Block-to-time mapping drift enables weight/reward misalignment

- **Location:** `LendingLedger.sol` : `update_market`; `setBlockTimeParameters`
- **Mechanism:** Reward epochs are block-based (`BLOCK_EPOCH`), but gauge weights are time-based (`GaugeController.WEEK`). `epochTime` is a linear estimate from `referenceBlockNumber`, `referenceBlockTime`, and `averageBlockTime`. If chain block times drift, or governance updates parameters without checkpointing all markets first (as the comment warns), the timestamp passed to `gauge_relative_weight_write` no longer corresponds to the block epoch being accrued.
- **Impact:** Systematic mispricing of gauge weights vs. reward epochs. Markets can be over- or under-paid relative to intended vote outcomes. This is exploitable in combination with the `block.number` bug above and parameter updates: rewards are assigned to the wrong point on the gauge weight timeline.

---

## Removed or unregistered markets still accrue with invalid gauge type

- **Location:** `GaugeController.sol` : `_gauge_relative_weight`; `LendingLedger.sol` : `update_market`
- **Mechanism:** `LendingLedger` continues to call `gauge_relative_weight_write(_market, ...)` for any whitelisted market. `_gauge_relative_weight` does not verify the gauge is registered; it uses `gauge_types_[_gauge] - 1`. For unregistered or removed gauges this is `-1`, reading `points_type_weight[-1][t]` and `points_weight[_gauge][t]` without validation.
- **Impact:** A whitelisted market without a valid `GaugeController` entry can accrue at weight `0` (lost rewards) or, after a broken `remove_gauge`, at corrupted type `-1` values. Users cannot fix weight via voting. Emissions are lost or misdirected depending on storage contents.

---

### Notes on scope

- **Governance centralization** (`setGovernance`, `toggleUnlockOverride`, `setRewards`, `setBlockTimeParameters`) is trusted-admin risk, not a permissionless attacker path, and is omitted per your criteria.
- **ERC777/callback reentrancy** on `LiquidityGauge.depositUnderlying` depends on a malicious or hook-bearing underlying token; not reported unless the deployed underlying is non-standard.
- **`VotingEscrow`**: The 255-week checkpoint iteration cap is a known liveness/decay limitation acknowledged in comments; it becomes a weight-decay issue only after ~5 years without interaction, not a typical exploit path.

The two highest-severity permissionless issues are **historical reward repricing via current gauge weights** and **gauge-wrapper emission farming without market TVL**. The **`remove_gauge` type `-1` corruption** is critical for protocol correctness whenever governance removes a gauge.

