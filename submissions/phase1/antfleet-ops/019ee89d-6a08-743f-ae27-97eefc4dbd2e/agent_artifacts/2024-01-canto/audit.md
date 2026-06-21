# Audit: 2024-01-canto

## Reward weight read with a block number where a UNIX timestamp is required
- Location: src/LendingLedger.sol : `update_market`
- Mechanism: The accrual loop derives `epoch = (i / BLOCK_EPOCH) * BLOCK_EPOCH`, where `i`/`BLOCK_EPOCH` are *block numbers* (100_000 ≈ 1 week of blocks), and then calls `gaugeController.gauge_relative_weight_write(_market, epoch)`. But `GaugeController._gauge_relative_weight` treats its second argument as a *UNIX timestamp*: it computes `t = (_time / WEEK) * WEEK` with `WEEK = 604800` seconds and reads `points_sum[t].bias` / `points_weight[_gauge][t].bias`. All gauge votes are stored at indices derived from `block.timestamp` (`((block.timestamp + WEEK)/WEEK)*WEEK`, in the ~1.6e9 range), while `floorToWeek(blockEpoch)` for any realistic block number lands in the tiny 1970-era index range (0, 604800, 1209600, …) that `_get_sum`/`vote_for_gauge_weights` never write. `total_weight` at those indices is therefore always 0, so `_gauge_relative_weight` returns 0 and every `cantoReward = (blockDelta * cantoPerBlock[epoch] * 0) / 1e18` is 0.
- Impact: No lending market ever accrues CANTO (`accCantoPerShare` stays flat), so the entire emission/reward mechanism is non-functional and all CANTO that governance funds into the ledger for lender rewards becomes permanently unclaimable/stranded.

## Vote-weight change cooldown (WEIGHT_VOTE_DELAY) is recorded but never enforced
- Location: src/GaugeController.sol : `vote_for_gauge_weights`
- Mechanism: The function writes `last_user_vote[msg.sender][_gauge_addr] = block.timestamp;` at the end, but unlike the Curve original it never enforces `require(block.timestamp >= last_user_vote[msg.sender][_gauge_addr] + WEIGHT_VOTE_DELAY)`. The stored value is dead (only the public getter reads it). Because re-voting is unrestricted, a voter can move their full voting power between gauges on every block instead of being committed for the ~10-day delay window, freely re-tuning `points_weight`/`points_sum` for each upcoming `next_time` boundary.
- Impact: A large veCANTO holder can repeatedly flip gauge weights with no cooldown to redirect emission/relative-weight allocation toward gauges that benefit them (e.g., chasing bribes or self-owned markets) and to grief other voters' allocations far faster than the protocol's intended rate limit allows.

