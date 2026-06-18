# Audit: 2024-01-canto

## Reward distribution always zero due to incorrect timestamp parameter
- Location: LendingLedger.sol : update_market
- Mechanism: The function computes `epoch` as a block number (e.g. 100000, 200000) and passes it directly to `gaugeController.gauge_relative_weight_write(_market, epoch)`. The GaugeController expects a UNIX timestamp in seconds, but receives a block number. Inside `gauge_relative_weight_write` the timestamp is floor‑divided by `WEEK` (7 days), producing `t = (epoch / WEEK) * WEEK`. For any realistic block number (orders of magnitude smaller than a real timestamp) this results in `t = 0`. The gauge weight is then read from `points_sum[0]` and `points_weight[_gauge][0]`, which are uninitialized (zero). Consequently `cantoReward` is always zero, and no rewards are ever distributed.
- Impact: The entire reward system is non‑functional. No CANTO rewards can ever be earned by any user, regardless of deposits or votes. The contract’s core purpose is completely broken.
