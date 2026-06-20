# Audit: 2024-03-neobase

## Reentrancy via unprotected ETH transfer in rewards claim
- Location: src/LendingLedger.sol : claim
- Mechanism: claim calls update_market then computes cantoToSend, updates only rewardDebt, and finally performs an unprotected low-level `msg.sender.call{value: ...}("")` with no ReentrancyGuard, no checks on reentrancy, and no state updates that would block subsequent calls to sync_ledger/update_market/vote paths.
- Impact: A malicious claiming contract can re-enter during the ETH transfer, call sync_ledger (with a whitelisted market) to arbitrarily mutate its own user.amount/market totals or another user's balances, then re-claim or checkpoint to obtain extra rewards or corrupt global epoch accounting.

## Missing access control on gauge weight removal
- Location: src/GaugeController.sol : remove_gauge_weight
- Mechanism: remove_gauge_weight is declared `public onlyGovernance` but is also reachable via the internal _remove_gauge_weight path from remove_gauge; the function unconditionally mutates points_weight/points_sum/changes_weight/changes_sum for any address that governance passes, without verifying the gauge still exists or that the caller is still governance after the first check.
- Impact: Governance (or a subsequently set governance address) can zero out weights and cancel slope changes for arbitrary addresses, allowing permanent theft of future CANTO distribution share from any gauge even after it was legitimately voted for.

## Integer underflow/overflow in slope accounting on gauge removal + vote
- Location: src/GaugeController.sol : _remove_gauge_weight and vote_for_gauge_weights
- Mechanism: _remove_gauge_weight performs unchecked `points_sum[...].slope -= old_weight_slope` and the 263-iteration loop does `changes_sum[...] -= gauge_weight_change` with only a one-sided `if >=` guard that sets to zero; vote_for_gauge_weights similarly uses Math.max on bias/slope but then unconditionally adds new_slope values and subtracts old ones across the same mappings.
- Impact: An attacker (or governance) that removes a gauge after users have voted can force underflows that zero legitimate slope change entries, causing future _get_sum/_get_weight calls to return inflated bias values and permanently mis-allocate CANTO emissions to the wrong gauges.

## Unbounded historical fill loops allow permanent desynchronization
- Location: src/GaugeController.sol : _get_total, _get_sum, _get_weight, _get_type_weight (and callers)
- Mechanism: All four internal checkpoint functions contain `for (uint256 i; i < 500; ++i)` loops that only advance time_weight/time_sum/etc. when `t > block.timestamp`; once 500 weeks have been missed the loop exits without updating time_* or points_total, leaving the next caller to start from stale values.
- Impact: After sufficient time (or deliberate governance delay), gauge_relative_weight and gauge_relative_weight_write return incorrect normalized weights; an attacker controlling a gauge can receive disproportionate CANTO inflation indefinitely because total_weight calculations never catch up.
