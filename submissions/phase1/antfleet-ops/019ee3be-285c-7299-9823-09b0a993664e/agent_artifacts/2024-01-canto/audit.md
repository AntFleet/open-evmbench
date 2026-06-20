# Audit: 2024-01-canto

**Incorrect timestamp vs block number usage in reward weight lookup**

- Location: LendingLedger.sol : update_market
- Mechanism: `update_market` computes `epoch = (i / BLOCK_EPOCH) * BLOCK_EPOCH` (a block number) and passes it directly as the `_time` argument to `gaugeController.gauge_relative_weight_write(_market, epoch)`. Inside GaugeController the value is immediately floored with `(_time / WEEK) * WEEK`, treating the block number as a Unix timestamp.
- Impact: Gauge relative weights are read from the wrong weekly slots (or from uninitialized slots that return 0), causing `cantoReward` to be computed incorrectly for every market. Rewards are therefore minted to the wrong gauges or lost entirely.

**Missing reentrancy protection on external call after state update**

- Location: LendingLedger.sol : claim
- Mechanism: `claim` performs `user.rewardDebt = accumulatedCanto` and then executes an unbounded `msg.sender.call{value:...}` without a reentrancy guard (or any mutex). `update_market` is only called once at the beginning.
- Impact: A malicious lending market or user contract can re-enter `claim` (or `sync_ledger`) before the CANTO transfer completes, potentially draining additional reward tokens if any other state (e.g., `accCantoPerShare`) can be influenced in the same transaction.

**Governance can arbitrarily overwrite any gauge weight, bypassing votes**

- Location: GaugeController.sol : _change_gauge_weight (called from add_gauge and remove_gauge_weight)
- Mechanism: `onlyGovernance` functions directly write `points_weight[_gauge][next_time].bias = _weight` and adjust `points_sum[next_time].bias` without consulting or invalidating existing `vote_user_slopes`.
- Impact: Governance can instantly redirect the entire CANTO distribution to attacker-controlled gauges or zero out legitimate ones, stealing all future rewards that users had voted for.

**Slope-change cleanup loop in gauge removal is bounded and can leave dangling deltas**

- Location: GaugeController.sol : _remove_gauge_weight
- Mechanism: The cleanup loop runs only `i < 263` weeks from `next_time`; any `changes_weight[_gauge][time_to_check]` entries beyond that window (or created after removal) are never zeroed, and the corresponding `changes_sum` entries are never subtracted.
- Impact: Future calls to `_get_sum` / `_get_weight` will apply stale positive or negative slope deltas, permanently corrupting global and per-gauge weight accounting and allowing incorrect reward weights to persist for years.

**No validation that a gauge still exists when writing vote slopes**

- Location: GaugeController.sol : vote_for_gauge_weights
- Mechanism: After the initial `isValidGauge` check (which only gates non-zero weights), the function still mutates `points_weight[_gauge_addr]`, `changes_weight[_gauge_addr]`, `points_sum`, and `changes_sum` even if governance has since called `remove_gauge`.
- Impact: Votes on a removed gauge still create live slope entries; subsequent weight calculations become inconsistent and an attacker can use removed gauges as sinks to waste or misdirect voting power.

**Unchecked external call for reward transfer with no fallback handling**

- Location: LendingLedger.sol : claim (and similarly VotingEscrow withdraw)
- Mechanism: `(bool success, ) = msg.sender.call{value: uint256(cantoToSend)}(""); require(success...)` performs an unbounded external call that can consume all gas or revert for reasons unrelated to the transfer (e.g., contract returning data > 0).
- Impact: A user whose claim would otherwise succeed can be permanently prevented from receiving CANTO if their fallback/receive logic is even slightly expensive, locking rewards in the contract forever.
