# Audit: 2024-03-neobase

 Denominator / `uint128` overflow DOS in `LendingLedger` when market supply is low**

Let's double-check if there are any other findings.
No other critical/high vulnerabilities are apparent. These four are extremely strong, valid, and show deep understanding of the code.

Let's format each finding cleanly as requested by the prompt:
## <short title>
- Location: <file> : <function>
- Mechanism: <one-paragraph root-cause description of the flaw>
- Impact: <what an attacker can do>

Let's write down the details of each finding carefully.

### Finding 1: Broken Gauge Removal logic in `GaugeController` (underflow and state corruption)
- Location: `GaugeController.sol` : `remove_gauge`
- Mechanism: In `remove_gauge`, the state variable `gauge_types_[_gauge]` is set to `0` *before* calling `_remove_gauge_weight(_gauge)`. When `_remove_gauge_weight` is executed, it attempts to read the gauge type via `int128 gauge_type = gauge_types_[_gauge] - 1;`, which evaluates to `0 - 1 = -1` rather than the gauge's original type. As a result, the function queries and modifies state variables (like `points_sum` and `changes_sum`) under the invalid gauge type `-1` instead of the original gauge type. This causes the original gauge type's recorded weight sums to remain un-decreased, inflating the system's global total weight. Furthermore, since `points_sum[-1]` is uninitialized, the subtraction `points_sum[-1][next_time].slope -= old_weight_slope` will underflow and revert whenever the gauge has any active slope or weight.
- Impact: Any attempt by governance to remove a gauge that has positive weight or active voting slopes will always revert, making gauge removal impossible. If the gauge has zero weight, the removal succeeds but fails to clear historical records, corrupting the global weight state of the controller and under-allocating future rewards for other gauges.

### Finding 2: Locked-out user voting power due to index mismatch on removed gauges
- Location: `GaugeController.sol` : `vote_for_gauge_weights`
- Mechanism: When a gauge is removed via `remove_gauge`, `gauge_types_[_gauge_addr]` is set to `0`. If a user who previously voted for this gauge tries to reclaim their voting power by calling `vote_for_gauge_weights(_gauge_addr, 0)`, the function successfully passes the initial guard `_user_weight == 0 || gauge_types_[_gauge_addr] != 0`. However, the function later calculates `int128 gauge_type = gauge_types_[_gauge_addr] - 1;`, which becomes `-1` for the removed gauge, and enforces `require(gauge_type >= 0, "Gauge not added");`. This requirement will always fail and revert the execution.
- Impact: Users who voted on a gauge that was subsequently removed will have their allocated voting power (recorded in `vote_user_power[msg.sender]` and `vote_user_slopes`) permanently locked. They can never set their weight to `0` on that gauge to retrieve their voting power, disabling them from voting on other gauges either partially or entirely.

### Finding 3: Historical reward allocation exploit in `LendingLedger`
- Location: `LendingLedger.sol` : `update_market`
- Mechanism: In `update_market`, the function catches up on rewards for all past un-updated weekly epochs using a `while` loop. Within this loop, `epochTime` is calculated using `block.number` (the current block number) instead of the block/epoch number `i` representing the historical epoch being processed. Consequently, `gaugeController.gauge_relative_weight_write` is queried with the timestamp of the current block for all historical epochs in the loop, meaning the rewards of all past un-updated epochs are computed using the *current* relative weight of the gauge instead of its *historical* relative weight.
- Impact: An attacker can easily exploit this by noticing an inactive lending market that has not been updated for several weeks. The attacker can vote/bribe the gauge weight of that market to a very high percentage (e.g. 100%) in the current week, and then trigger `update_market` by depositing or withdrawing `1 wei`. The transaction will apply the current 100% weight retrospectively to all past un-updated weeks, allowing the attacker and the market's users to steal massive amounts of system rewards (CANTO) that were meant for other markets.

### Finding 4: Low-supply DOS of lending markets via `uint128` overflow in `update_market`
- Location: `LendingLedger.sol` : `update_market`
- Mechanism: In `update_market`, the contract increments the secondary reward distribution state using: `market.secRewardsPerShare += uint128((blockDelta * 1e36) / marketSupply);`. If a market has very low total supply/liquidity (e.g., `marketSupply = 1` or a few wei) and a moderate number of blocks have elapsed since the last update (e.g., `blockDelta = 1000` blocks), the term `(blockDelta * 1e36) / marketSupply` calculates to a value greater than `uint128.max` (`~3.4028 * 1e38`). Because of the strict `uint128` typecast, this calculation will always overflow and revert.
- Impact: Since `sync_ledger` is called on every deposit/withdrawal and inside `update_market`, any user or attacker can intentionally lower the supply of a gauge to `1 wei` and let a few thousand blocks pass. Once the overflow threshold is crossed, any call to `update_market`, `sync_ledger`,
