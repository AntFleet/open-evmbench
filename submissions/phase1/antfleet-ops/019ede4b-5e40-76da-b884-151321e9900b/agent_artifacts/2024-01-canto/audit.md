# Audit: 2024-01-canto

## Critical: Block Number Passed as Timestamp to GaugeController
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: The `update_market` function calculates `epoch` as a block number (`(i / BLOCK_EPOCH) * BLOCK_EPOCH`) and passes it to `gaugeController.gauge_relative_weight_write(_market, epoch)`. However, `GaugeController` expects a Unix timestamp and floors it to weekly intervals using `WEEK` (604,800 seconds). Passing a block number (e.g., 10,000,000) results in the controller evaluating the gauge weight at a timestamp in 1970 (e.g., ~9.6 million seconds), where no votes or weights exist.
- Impact: The gauge relative weight will always evaluate to 0, causing `cantoReward` to be 0. As a result, no CANTO rewards will ever be calculated or distributed to any lending market, completely breaking the protocol's incentive mechanism.

## High: Incorrect Epoch Boundary Calculation in Reward Loop
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: In the reward accumulation loop, the next epoch boundary is calculated as `nextEpoch = i + BLOCK_EPOCH` instead of the correct `epoch + BLOCK_EPOCH`. When `market.lastRewardBlock` is not a perfect multiple of `BLOCK_EPOCH` (which is almost always the case since it's initialized to the current `block.number`), the loop will incorrectly apply the current epoch's `cantoPerBlock` rate to blocks that actually belong to the subsequent epoch.
- Impact: Reward distribution rates will be misaligned with their intended epochs. If governance changes the `cantoPerBlock` rate, markets will receive incorrect reward amounts for blocks spanning across the epoch boundary, leading to over-distribution or under-distribution of funds.

## High: Silent Truncation of Accumulated Rewards per Share
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: The `accCantoPerShare` is updated using an explicit cast: `uint128((cantoReward * 1e18) / marketSupply)`. In Solidity 0.8+, explicit casts to smaller integer types do not revert on overflow; they silently truncate the higher bits. If a market has a very small `marketSupply` and a large `cantoReward`, the calculated value can exceed `type(uint128).max` (~3.4e38).
- Impact: The `accCantoPerShare` value will silently wrap around to a drastically smaller number. This breaks the MasterChef-style reward accounting, causing users to lose their accrued rewards and creating severe accounting discrepancies between the contract's actual ETH balance and the tracked reward debts.

## High: Unsigned Integer Underflow in GaugeController Slope Decay
- Location: `src/GaugeController.sol` : `_get_sum` / `_get_weight`
- Mechanism: The checkpoint loops decay the slope using unsigned integer subtraction: `pt.slope -= d_slope`, where `d_slope` is the scheduled slope change (`changes_sum[t]`). Unlike the original Curve Vyper implementation which uses signed integers, this Solidity port uses `uint256`. If `d_slope` exceeds `pt.slope` due to rounding errors, partial gauge removals, or inconsistent state updates during `_remove_gauge_weight`, the subtraction will underflow.
- Impact: The underflow will cause the transaction to revert. Since `_get_sum` and `_get_weight` are called during core operations like `checkpoint`, `vote_for_gauge_weights`, and `gauge_relative_weight_write`, a single underflow will permanently brick the `GaugeController`, halting all voting, weight updates, and reward distributions.
