# Audit: 2024-03-neobase

I have both reports inline and the task is a careful merge — matching findings by root cause and code path, not wording. Let me map them before writing.

**Matching analysis:**
- A's "uint128 truncation" ＝ B's "Per-Share Accumulators Truncate To uint128" → same root cause (`update_market`) → **consensus**
- A's "Historical epochs valued at current gauge weight" ＝ B's "Historical Rewards Use Current Gauge Weight" → same `epochTime` bug in `update_market` → **consensus**
- A's "mints 1:1 / non-standard tokens" ＝ B's "Fee-On-Transfer Tokens Overmint Gauge Shares" → same `depositUnderlying` overmint → **consensus**
- A's "De-whitelisting freezes funds" → only A (B's truncation finding mentions `_afterTokenTransfer` blocking, but that's the truncation root cause, not de-whitelisting) → **A only**
- B's "Gauge Removal Uses Cleared Type", "Removed Gauges Cannot Be Unvoted", "Emergency Unlock Leaves Gauge Votes Active" → only B → **B only**

Here is the merged report.

---

# Merged Security Audit Report

## Consensus findings

## Silent `uint128` truncation in reward-per-share accumulators
*(consensus)*
- Location: `src/LendingLedger.sol` : `update_market` — the two accumulator updates:
  - `market.accCantoPerShare += uint128((blockDelta * cantoPerBlock[epoch] * gaugeController.gauge_relative_weight_write(_market, epochTime)) / marketSupply);`
  - `market.secRewardsPerShare += uint128((blockDelta * 1e36) / marketSupply);`
- Mechanism: `accCantoPerShare`/`secRewardsPerShare` are declared `uint128` in `MarketInfo`, but each per-iteration term is computed in `uint256` and then cast down with `uint128(...)`, silently dropping the high bits before the storage addition. The `accCantoPerShare` numerator `blockDelta * cantoPerBlock[epoch] * relativeWeight` can reach roughly `1e5 * 1e18 * 1e18 = 1e41`, and `secRewardsPerShare`'s numerator `blockDelta * 1e36 ≈ 1e41`; both exceed `type(uint128).max` (~3.4e38) when `marketSupply` is small. `marketSupply` is attacker-influenceable — it is just the sum of depositor balances, so any user can make themselves the sole depositor with a tiny balance (e.g. 1 wei). The wrapped value corrupts the monotonic, shared accumulator; in other cases the subsequent checked `uint128` addition can also overflow and revert, bricking future `update_market` calls.
- Impact: An attacker stakes dust in a low-liquidity rewarded market, lets an epoch elapse, and triggers the truncation, permanently corrupting the shared `accCantoPerShare`. If the wrapped value comes out *larger* than correct, a later `claim` (`accumulatedCanto = user.amount * accCantoPerShare / 1e18 - rewardDebt`) pays more CANTO than fair share, draining rewards earmarked for other markets; if *smaller*, rewards are stranded. If the checked addition reverts, `update_market` bricks. For gauge-backed markets this can additionally block transfers/withdrawals, because `LiquidityGauge._afterTokenTransfer` requires `sync_ledger` (→ `update_market`) to succeed. Reachable even without an attacker whenever a market's total balance is small relative to the configured `cantoPerBlock`.

## Historical epochs are valued at the *current* gauge weight, breaking reward conservation
*(consensus)*
- Location: `src/LendingLedger.sol` : `update_market` — the `epochTime` computation and `gaugeController.gauge_relative_weight_write(_market, epochTime)` inside the catch-up `while` loop.
- Mechanism: The loop walks each elapsed epoch from `market.lastRewardBlock`, but `epochTime = referenceBlockTime + ((block.number - referenceBlockNumber) * averageBlockTime) / 1000` is derived from the *current* `block.number`, not from the loop index/epoch being processed. It is therefore constant across all iterations and always approximates "now". `gauge_relative_weight_write` then reads the weight for the current week (`_gauge_relative_weight` floors `epochTime` to the week and reads `points_total[t]`/`points_weight[_gauge][t]`) and applies it to rewards belonging to past epochs. Because gauge weights change over time (governance `change_gauge_weight`, other users' `vote_for_gauge_weights`) without triggering `update_market` for this market, the back-dated weight is wrong; and since each market is caught up at its own `lastRewardBlock`/time, the per-market relative weights used for the same historical block no longer sum to 1e18.
- Impact: Reward distribution is not conservative. An attacker keeps dust supply in a market, waits until rewards accumulate without `update_market`, votes weight to that market, then checkpoints and claims rewards for past epochs at the new (inflated) weight. A market whose weight recently increased over-accrues for past blocks, so total CANTO claimable across all markets for a block range can exceed `cantoPerBlock`, leaving the ledger insolvent and causing later claimants' transfers to fail or under-pay. Preconditions: the market had nonzero supply and was not updated for prior epochs.

## LiquidityGauge mints shares 1:1 without accounting for non-standard underlying tokens
*(consensus)*
- Location: `src/LiquidityGauge.sol` : `depositUnderlying` (and `withdrawUnderlying`)
- Mechanism: `depositUnderlying` does `IERC20(underlyingToken).safeTransferFrom(_user, address(this), _amount); _mint(_user, _amount);` — it mints exactly `_amount` shares regardless of how many tokens were actually received, with no balance-delta check. For a fee-on-transfer or rebasing underlying the gauge receives less than `_amount` but credits the full `_amount` to the user (and to `lendingMarketTotalBalance` via `sync_ledger`). `withdrawUnderlying` later burns and `safeTransfer`s the full nominal `_amount`.
- Impact: If a fee-on-transfer, rebasing, or otherwise non-exact ERC20 is whitelisted as an underlying, the gauge becomes under-collateralized: an attacker (or early/large withdrawers) can withdraw more underlying than was actually deposited, draining other users' deposited tokens, while the last withdrawers cannot redeem (funds lost / DoS). Precondition: governance whitelists such a token; the standard Canto lending-market token is not expected to be fee-on-transfer, but the gauge makes no defensive check.

---

## Additional findings (single-reviewer)

## De-whitelisting a market permanently freezes all funds in its LiquidityGauge (and blocks claims)
*(Reviewer A only)*
- Location: `src/LiquidityGauge.sol` : `_afterTokenTransfer` / `withdrawUnderlying`, coupled with `src/LendingLedger.sol` : `update_market` (the `require(lendingMarketWhitelist[_market], "Market not whitelisted")` guard) and `sync_ledger`.
- Mechanism: Every mint, burn, and transfer of the gauge ERC-20 routes through `_afterTokenTransfer`, which unconditionally calls `LendingLedger.sync_ledger(...)`. `sync_ledger` calls `update_market(lendingMarket)`, whose first statement is `require(lendingMarketWhitelist[_market], "Market not whitelisted")`. `withdrawUnderlying` performs `_burn(_user, _amount)` *before* returning the underlying, and the burn triggers `_afterTokenTransfer(user, address(0), amount)` → `sync_ledger(user, -amount)` → `update_market` → revert. No gauge code path returns underlying without first calling `sync_ledger`. Governance can flip a market to non-whitelisted at any time via `whiteListLendingMarket(_market, false, _)` (the only requirement is that the value actually changes).
- Impact: As soon as a gauge-backed market is de-whitelisted (a routine or temporary governance toggle), `withdrawUnderlying` reverts for every holder, making the deposited underlying permanently unrecoverable. The same `require` makes `claim` and `sync_ledger` revert, so already-accrued CANTO rewards become unclaimable for both gauge and direct markets after de-whitelisting. A single governance action (or compromised/misconfigured governance) bricks user withdrawals with no recovery path.

## Gauge removal reads a cleared gauge type
*(Reviewer B only)*
- Location: `src/GaugeController.sol` : `remove_gauge`, `_remove_gauge_weight`
- Mechanism: `remove_gauge` sets `gauge_types_[_gauge] = 0` *before* calling `_remove_gauge_weight`. `_remove_gauge_weight` then derives `gauge_type = gauge_types_[_gauge] - 1`, which becomes `-1` instead of the gauge's original type. Weight removal therefore reads/writes the wrong type bucket and can underflow when subtracting the gauge's old weight.
- Impact: Any gauge with active weight can make direct removal revert, or corrupt accounting under the `-1` type bucket. Preconditions: governance attempts to remove a gauge that still has recorded weight.

## Removed gauges cannot be unvoted
*(Reviewer B only)*
- Location: `src/GaugeController.sol` : `vote_for_gauge_weights`
- Mechanism: The function appears to allow `_user_weight == 0` for removed gauges, but later unconditionally computes `gauge_type = gauge_types_[_gauge_addr] - 1` and requires `gauge_type >= 0`. Once a gauge is removed (`gauge_types_` cleared to 0), this check fails, so users cannot call the function to clear their old vote.
- Impact: Users who voted for a removed gauge have `vote_user_power` permanently consumed, preventing them from reusing that voting power. Preconditions: a gauge is removed while users still have active votes on it.

## Emergency unlock leaves gauge votes active
*(Reviewer B only)*
- Location: `src/VotingEscrow.sol` : `withdraw`; `src/GaugeController.sol` : `vote_for_gauge_weights`
- Mechanism: `unlockOverride` lets users withdraw before their original lock end, but `GaugeController` keeps independent scheduled slopes in `vote_user_slopes`, `points_weight`, and `changes_weight`. Withdrawal does not clear or reduce those gauge votes.
- Impact: After governance enables emergency unlock, users can withdraw locked CANTO while their prior gauge votes continue affecting rewards until the original lock end. A user with liquidity in the voted market can keep directing emissions without maintaining the escrowed position.

