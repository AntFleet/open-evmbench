# Audit: 2024-01-canto

# Security Audit Report

Findings below are limited to genuine security issues (logic, accounting, access control, reentrancy, oracle/timebase misuse). Ordered by severity.

---

## Block number passed as timestamp for gauge weights

- **Location:** `LendingLedger.sol` : `update_market`
- **Mechanism:** Reward accrual aligns epochs by **block number** (`BLOCK_EPOCH = 100_000`), but gauge share is fetched with that same value as `_time`:

```solidity
uint256 epoch = (i / BLOCK_EPOCH) * BLOCK_EPOCH;
// ...
gaugeController.gauge_relative_weight_write(_market, epoch)
```

`GaugeController._gauge_relative_weight` treats `_time` as a **Unix timestamp** and floors it with `WEEK = 7 days`:

```solidity
uint256 t = (_time / WEEK) * WEEK;
```

For essentially all realistic block heights (e.g. `100_000`, `500_000`, …), `t` becomes `0` or other meaningless early-1970 weeks that do not correspond to when votes were recorded. Votes are scheduled at real timestamps (`next_time = ((block.timestamp + WEEK) / WEEK) * WEEK)`), so lookup keys never match live voting state.

- **Impact:** CANTO emissions are mis-accounted. In the typical case `points_sum[0].bias == 0`, so `gauge_relative_weight` returns `0`, `cantoReward` is always `0`, and `accCantoPerShare` never increases while `lastRewardBlock` still advances — **rewards are silently forfeited** and ETH/CANTO sent to `LendingLedger` becomes stuck/unallocatable. In edge cases where an ancient week bucket has nonzero weight, the wrong market could receive a disproportionate share.

---

## Emission griefing via zero market supply

- **Location:** `LendingLedger.sol` : `update_market`
- **Mechanism:** When `lendingMarketTotalBalance[_market] == 0`, the reward loop is skipped but `lastRewardBlock` is always set to `block.number`:

```solidity
if (marketSupply > 0) {
    while (i < block.number) { /* accrue rewards */ }
}
market.lastRewardBlock = uint64(block.number);
```

`update_market` is **public**; any address can invoke it for a whitelisted market.

- **Impact:** If an attacker is (even briefly) the sole depositor, they can withdraw all cNOTE (triggering `sync_ledger` → `update_market`) or call `update_market` directly while supply is `0`, advancing `lastRewardBlock` without accruing rewards for that block range. Those emissions are **permanently lost** for all past and future LPs of that market. This is a griefing attack on protocol emissions, not theft of existing balances.

---

## `accCantoPerShare` / `secRewardsPerShare` uint128 overflow bricks markets

- **Location:** `LendingLedger.sol` : `update_market`
- **Mechanism:** Accumulators are `uint128` and updated via unchecked downcast:

```solidity
market.accCantoPerShare += uint128((cantoReward * 1e18) / marketSupply);
market.secRewardsPerShare += uint128((blockDelta * 1e18) / marketSupply);
```

In Solidity 0.8+, casting a value above `type(uint128).max` **reverts**.

- **Impact:** Once cumulative rewards push either accumulator past `2^128 - 1`, every `update_market` call reverts. That blocks `sync_ledger` (deposits/withdrawals) and `claim` for the affected market — a **permanent DoS** on core lending-market operations until deployment of a new ledger and migration.

---

## Stale gauge weights when checkpoint loops are exhausted

- **Location:** `GaugeController.sol` : `_get_sum`, `_get_weight`; `VotingEscrow.sol` : `_checkpoint`
- **Mechanism:** Both contracts cap forward-filling of time series:
  - `GaugeController`: max **500** weekly steps; `time_sum` / `time_weight` are only updated when the loop reaches a week **beyond** `block.timestamp`.
  - `VotingEscrow`: max **255** weekly steps in `_checkpoint` (comment acknowledges vote weight can break).

If nobody checkpoints for longer than these horizons, loops exit early while `time_sum` / global VE state remain stale. `_gauge_relative_weight` then reads outdated `points_sum[t].bias` and `points_weight[gauge][t].bias`.

- **Impact:** Incorrect relative gauge weights → **wrong reward splits** across lending markets until someone runs enough checkpoint transactions. An attacker does not need privileges; they benefit if their market’s stale weight is overstated relative to others. This is a logic/accounting flaw in the weight oracle used by `LendingLedger`.

---

## Active lock required to clear votes (`vote_for_gauge_weights`)

- **Location:** `GaugeController.sol` : `vote_for_gauge_weights`
- **Mechanism:** Every vote path, including setting weight to `0`, requires:

```solidity
require(lock_end > next_time, "Lock expires too soon");
```

After a `VotingEscrow` lock expires, the user cannot call `vote_for_gauge_weights(..., 0)` until they create a **new** lock. Until then, `vote_user_power[msg.sender]` still counts power allocated to gauges whose on-chain weight has already decayed at `lock_end`.

- **Impact:** Self-DoS on voting: a user who unlocks without first zeroing votes must `createLock` again before they can free `vote_user_power` and vote elsewhere. If they re-lock and allocate to a new gauge without clearing old entries, they hit `"Used too much power"` even though decayed votes no longer contribute meaningful weight — **voting power accounting desync** that blocks legitimate votes until manual cleanup on every previously voted gauge.

---

## `remove_gauge_weight` leaves gauge “valid” with zero weight

- **Location:** `GaugeController.sol` : `remove_gauge_weight`
- **Mechanism:** `remove_gauge` sets `isValidGauge[_gauge] = false` and calls `_remove_gauge_weight`. `remove_gauge_weight` only calls `_remove_gauge_weight` and does **not** flip `isValidGauge`. Governance can therefore zero a gauge’s weight while it remains whitelisted as a valid voting target.

- **Impact:** Users can still allocate `vote_user_power` to a gauge governance intended to disable (nonzero votes on a gauge with administratively zeroed weight). Vote bookkeeping and `changes_weight` / `changes_sum` can be driven into inconsistent states; `_remove_gauge_weight` may **revert on slope underflow** (`points_sum[next_time].slope -= old_slope`) if weights were re-voted after a partial removal, **bricking gauge removal** and leaving reward weights unpredictable.

---

## `claim` does not enforce “finished epoch only” (documentation mismatch → fairness risk)

- **Location:** `LendingLedger.sol` : `claim`
- **Mechanism:** NatSpec states claims are only for prior/finished epochs, but `claim` calls `update_market` through the current block and immediately pays `accumulatedCanto - rewardDebt` with no epoch guard.

- **Impact:** Users can claim rewards accruing in the **current** block epoch while gauge weights for that epoch may still change (votes, `remove_gauge`, checkpoint lag). Early claimers can extract CANTO at a snapshot before weights finalize; later LPs subsidize them — **unfair reward extraction** / slow governance or voter manipulation of intra-epoch weights.

---

## Insolvent `claim` bricks withdrawals for late claimers

- **Location:** `LendingLedger.sol` : `claim`
- **Mechanism:** Claims pay native token from the contract balance with no cap on total liabilities vs. `address(this).balance`:

```solidity
(bool success, ) = msg.sender.call{value: uint256(cantoToSend)}("");
require(success, "Failed to send CANTO");
```

- **Impact:** If accounting over-allocates (e.g., inflated gauge weight from stale checkpoints, governance setting high `cantoPerBlock`, or insufficient funding), early claimers drain the contract and **later `claim` calls revert**, leaving users with updated `rewardDebt` but no tokens — classic reward-contract insolvency (not exploitable without inflated accrual or missing funding, but a real fund-loss path).

---

## Whitelisted lending market controls reward denominator

- **Location:** `LendingLedger.sol` : `sync_ledger`
- **Mechanism:** `lendingMarketTotalBalance` is incremented purely from `_delta` reported by `msg.sender` (the market). The only sanity check is non-negative aggregate balance; there is no cross-check against actual cNOTE locked in the market contract.

- **Mechanism:** A compromised or malicious **whitelisted** market can inflate `lendingMarketTotalBalance` without matching deposits, diluting `accCantoPerShare` for honest users, or deflate it to capture outsized rewards.

- **Impact:** **Theft of emissions** from honest LPs if governance whitelists a malicious/buggy market. This is a trust-boundary flaw in the security model, not permissionless attacker access.

---

## `remove_gauge` slope cleanup limited to 263 weeks

- **Location:** `GaugeController.sol` : `_remove_gauge_weight`
- **Mechanism:** When removing a gauge, scheduled per-gauge slope changes are cleared only for `next_time + i * WEEK` where `i < 263` (~5 years). This matches max `LOCKTIME` only if no clock skew, extensions, or prior manual weight edits leave changes beyond that window.

- **Impact:** If residual `changes_weight` / `changes_sum` entries remain beyond the loop horizon, future `_get_sum` / `_get_weight` can apply incorrect slope deltas → **global or per-gauge weight drift** and misallocated CANTO via `LendingLedger` (lower severity if loop coverage is sufficient in practice; still a real edge-case logic bug).

---

## Notes on excluded items

- **`Turnstile.sol`:** Interface only; unused in the provided code — no vulnerability.
- **VotingEscrow reentrancy:** `nonReentrant` on value-moving entrypoints; `rewardDebt` updated before ETH send in `LendingLedger.claim` — no classic reentrancy drain identified.
- **Secondary rewards:** `secRewardDebt` is accrued but never paid; incomplete feature, not an exploitable theft path in this scope.
- **Governance centralization** (`setGovernance`, `setRewards`, whitelist): trusted-admin assumptions, not reported as standalone findings.

---

### Highest-priority fix

The **block-number / timestamp confusion** in `LendingLedger.update_market` is the most severe issue: it breaks the core link between `GaugeController` voting and emissions. Weights should be queried at the **timestamp** corresponding to each reward period (or the system should use one consistent timebase for both voting and rewards). I can outline a concrete fix pattern if you want to implement it in Agent mode.

