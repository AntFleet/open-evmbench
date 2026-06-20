# Audit: 2024-01-canto

## LendingLedger passes block-epoch numbers as Unix timestamps to GaugeController
- **Location:** `src/LendingLedger.sol` : `update_market`
- **Mechanism:** `update_market` computes `epoch` as a block-number multiple of `BLOCK_EPOCH` (`(i / BLOCK_EPOCH) * BLOCK_EPOCH`) and passes it to `gaugeController.gauge_relative_weight_write(_market, epoch)`. Inside `GaugeController`, `_gauge_relative_weight` treats that value as a Unix timestamp and computes `uint256 t = (_time / WEEK) * WEEK`. Because `WEEK = 604800` seconds, for any realistic block number `epoch` is interpreted as a timestamp in early 1970, long before the controller existed, so `points_sum[t].bias` and `points_weight[_gauge][t].bias` are uninitialized/zero.
- **Impact:** `gauge_relative_weight_write` returns `0` for every block epoch processed, so `cantoReward` is always zero and lending markets never accrue CANTO rewards. The `CANTO` sent to the ledger becomes undistributable, regardless of configured `cantoPerBlock` or gauge voting weights.

## LendingLedger market checkpoint can run out of block gas after long inactivity
- **Location:** `src/LendingLedger.sol` : `update_market`
- **Mechanism:** `update_market` advances one `BLOCK_EPOCH` per loop iteration and calls `gauge_relative_weight_write` every iteration; that external call itself executes `_get_weight` and `_get_sum`, which walk forward week-by-week. If a market is not interacted with for many epochs, the cumulative gas cost of the nested loops can exceed the block gas limit.
- **Impact:** Any subsequent `sync_ledger` or `claim` for that market will revert in `update_market`, bricking deposits/withdrawals/rewards for the market. Because the lending market relies on `sync_ledger` for user accounting, this can trap user funds in the downstream market contract.

## GaugeController checkpoint loops cannot advance beyond 500 missed weeks
- **Location:** `src/GaugeController.sol` : `_get_sum`, `_get_weight`
- **Mechanism:** Both functions cap their fill loop at `500` iterations and only update `time_sum`/`time_weight` when `t > block.timestamp`. If more than 500 weeks pass without a checkpoint, the loop exhausts while `t` is still ≤ `block.timestamp`, so the time pointer is not advanced.
- **Impact:** On every future call the function starts from the same stale pointer and recomputes the same 500-week window, leaving gauge and total weights permanently stale and inconsistent with the current voting state.

## GaugeController gauge removal can revert on slope underflow
- **Location:** `src/GaugeController.sol` : `_remove_gauge_weight`
- **Mechanism:** The function subtracts `old_slope` from `points_sum[next_time].slope` and, in the cleanup loop, subtracts `gauge_weight_change` from `changes_sum[time_to_check]` without any underflow guards. Under inconsistent slope state this can underflow.
- **Impact:** `remove_gauge(...)`, the only governance path to remove a gauge, will revert if slope bookkeeping is inconsistent. This can permanently prevent governance from removing a malicious or deprecated gauge.

## LendingLedger `claim` distributes up to the current block despite epoch-restriction comment
- **Location:** `src/LendingLedger.sol` : `claim`
- **Mechanism:** The function’s docstring states that “Claim the CANTO … Can only be performed for prior (i.e. finished) epochs, not the current one”, but it simply calls `update_market(_market)`, which advances `accCantoPerShare` all the way to `block.number`. No check prevents including the current, incomplete epoch.
- **Impact:** Users can claim rewards for the current, still-running epoch. Any other logic or off-chain accounting that assumes the stated prior-epoch-only invariant can be broken.
