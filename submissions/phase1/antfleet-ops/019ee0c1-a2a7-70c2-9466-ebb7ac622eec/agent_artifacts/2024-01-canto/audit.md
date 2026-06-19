# Audit: 2024-01-canto

Found 2 genuine reward-accounting vulnerabilities.

## Gauge weights are looked up with block numbers instead of timestamps
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: `epoch` is derived from `block.number` using `BLOCK_EPOCH`, but it is passed to `gaugeController.gauge_relative_weight_write(_market, epoch)`, whose `_time` parameter is treated as a Unix timestamp and rounded by `WEEK`. Gauge weights are stored by timestamp weeks, not block-number epochs, so the ledger usually queries empty historical buckets and receives weight `0`.
- Impact: Any account can call `update_market(_market)` for a whitelisted market, or trigger it through `claim`, causing `lastRewardBlock` to advance while accruing zero CANTO. This permanently skips rewards for those blocks, preventing suppliers from receiving emissions and leaving funded CANTO undistributed.

## Reward epochs are advanced from the last update, not the epoch boundary
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: Inside the reward loop, `nextEpoch` is calculated as `i + BLOCK_EPOCH` instead of `epoch + BLOCK_EPOCH`. If `market.lastRewardBlock` is not exactly aligned to a `BLOCK_EPOCH` boundary, the previous epoch’s `cantoPerBlock` and gauge weight are applied past the real boundary for up to almost a full epoch.
- Impact: Anyone can time public `update_market` calls so a favorable old epoch rate/weight is applied into the next epoch, overpaying a market and draining more CANTO than intended. Conversely, an unfavorable old epoch can be extended to underpay/grief suppliers. This is currently masked in many deployments by the timestamp/block-number bug above, but it is a separate accounting flaw in the same code path.

