# Audit: 2024-03-neobase

## Gauge weight uses current bias instead of future bias
- **Location:** `src/GaugeController.sol` : `vote_for_gauge_weights`
- **Mechanism:** When a user votes, the function needs to update the gauge’s weight (bias) at the start of the next weekly epoch (`next_time`). It calls `_get_weight(_gauge_addr)` to obtain the current bias, then uses that value directly in the calculation `Math.max(old_weight_bias + new_bias, old_bias) - old_bias` to set `points_weight[_gauge_addr][next_time].bias`. The correct bias at `next_time` is `current_bias - decay`, where `decay` is the natural reduction of bias from now until `next_time`. Because the decay is ignored, the stored bias at `next_time` is systematically overstated. The same pattern exists in `_change_gauge_weight` and `_change_type_weight`, but those are governance‑only.
- **Impact:** Any user can vote to inflate the gauge’s weight for the upcoming epoch. This skews the gauge’s relative weight, causing it to receive a disproportionately large share of CANTO rewards in the `LendingLedger`, effectively stealing rewards from legitimate users of other gauges.

## Vote‑withdrawal from removed gauges is broken
- **Location:** `src/GaugeController.sol` : `vote_for_gauge_weights`
- **Mechanism:** The function intends to allow calling `vote_for_gauge_weights(_gauge_addr, 0)` on a gauge that has been removed (i.e., `gauge_types_[_gauge_addr] == 0`) to clear the user’s vote. However, immediately after the check `require(_user_weight == 0 || gauge_types_[_gauge_addr] != 0, ...)`, the code computes `int128 gauge_type = gauge_types_[_gauge_addr] - 1;` (which becomes `-1`) and then performs `require(gauge_type >= 0, "Gauge not added");`. This always reverts when `_gauge_addr` is not a valid gauge, making it impossible to withdraw voting power from a removed gauge.
- **Impact:** Users who have voted for a gauge that later gets removed cannot reclaim their allocation. Their voting power remains locked in the old gauge, preventing them from using it on other gauges and reducing the overall voting participation.
