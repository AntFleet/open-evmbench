# Audit: 2024-01-canto

## Broken CANTO Reward Accounting From Block/Time Epoch Mismatch

- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: `LendingLedger` computes `epoch` from `block.number` using `BLOCK_EPOCH`, then passes that value into `GaugeController.gauge_relative_weight_write(_market, epoch)`. `GaugeController` interprets `_time` as a Unix timestamp and floors it by `WEEK`. As a result, normal block-number epochs like `100000`, `200000`, etc. are looked up as timestamps near 1970, where no gauge weights exist. The returned relative weight is therefore zero, and `update_market` still advances `market.lastRewardBlock`.
- Impact: Any caller can trigger `update_market`, `claim`, or a market sync path and permanently skip CANTO rewards for the elapsed blocks. Whitelisted lending markets receive zero CANTO emissions despite configured `cantoPerBlock` and gauge votes, leaving reward funds undistributed/stuck and breaking the incentive system.

## Reward Epoch Boundary Misaccounting

- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: Inside the reward loop, `epoch` is computed as the floored epoch start, but `nextEpoch` is set to `i + BLOCK_EPOCH` instead of `epoch + BLOCK_EPOCH`. If `market.lastRewardBlock` is not exactly aligned to a `BLOCK_EPOCH` boundary, the loop applies the starting epoch’s reward rate and gauge weight past the real epoch boundary. This misprices blocks from the next epoch and then advances `lastRewardBlock`, preventing later correction.
- Impact: A caller can update a market after an epoch boundary and cause rewards to be overpaid or underpaid depending on whether the previous epoch’s rate/weight was higher or lower than the new one. Majority suppliers can extract excess CANTO from the reward pool, while other users can be underpaid.

## Reward Indices Can Truncate Or Revert For Low Market Supply

- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: `accCantoPerShare` and `secRewardsPerShare` are stored as `uint128`, but the per-share increments are computed in `uint256` and then explicitly cast to `uint128`. Solidity does not protect explicit narrowing casts from truncation. With low `marketSupply` and sufficiently large elapsed rewards, `(cantoReward * 1e18) / marketSupply` or `(blockDelta * 1e18) / marketSupply` can exceed `uint128.max`, causing silent truncation before addition or a checked overflow on the subsequent `uint128` addition.
- Impact: An attacker who can reduce a whitelisted market’s accounted supply to a tiny amount can corrupt or halt reward accounting for that market. Rewards may be permanently under-accounted, or `update_market` can revert and block claims/deposit/withdraw syncs that depend on it.

