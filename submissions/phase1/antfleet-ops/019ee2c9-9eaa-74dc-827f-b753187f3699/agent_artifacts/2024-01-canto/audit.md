# Audit: 2024-01-canto

## Gauge weights are queried with block numbers instead of timestamps
- Location: [LendingLedger.sol](/Users/augstar/open-evmbench/audit_sources/2024-01-canto/src/LendingLedger.sol:56) : `update_market`
- Mechanism: `update_market` derives `epoch` from `block.number` (`(i / BLOCK_EPOCH) * BLOCK_EPOCH`) and passes it into `gaugeController.gauge_relative_weight_write(_market, epoch)`. The `GaugeController` does not key weights by block number; it records and reads them by weekly UNIX timestamps (`next_time = ((block.timestamp + WEEK) / WEEK) * WEEK`, then `t = (_time / WEEK) * WEEK`). On Canto, block-number epochs like `500000` do not match timestamp buckets like `1700000000`, so the ledger queries empty `points_sum[t]` / `points_weight[_gauge][t]` slots and gets a zero relative weight.
- Impact: voted markets do not accrue CANTO at all. Users can deposit into a valid whitelisted market and still be unable to earn the configured emissions because the reward path reads from the wrong time domain.

## Reward accrual crosses epoch boundaries with the wrong rate and weight
- Location: [LendingLedger.sol](/Users/augstar/open-evmbench/audit_sources/2024-01-canto/src/LendingLedger.sol:64) : `update_market`
- Mechanism: the loop computes the current epoch correctly as `epoch = (i / BLOCK_EPOCH) * BLOCK_EPOCH`, but then uses `nextEpoch = i + BLOCK_EPOCH` instead of `epoch + BLOCK_EPOCH`. Because `lastRewardBlock` is usually not aligned to `BLOCK_EPOCH`, each iteration spans past the real epoch boundary while still pricing the entire span with `cantoPerBlock[epoch]` and the gauge weight for that earlier epoch. The cursor stays misaligned forever, so every later update keeps attributing part of one epoch’s blocks to the neighboring epoch’s parameters.
- Impact: whenever emissions change across epochs, users staked through the boundary are overpaid or underpaid for a large slice of blocks. An attacker who keeps funds in a market across a high-rate to low-rate transition can continue receiving the stale higher rate after the boundary.

## `accCantoPerShare` silently truncates on overflow
- Location: [LendingLedger.sol](/Users/augstar/open-evmbench/audit_sources/2024-01-canto/src/LendingLedger.sol:67) : `update_market`
- Mechanism: `market.accCantoPerShare` is a `uint128`, but the increment `(cantoReward * 1e18) / marketSupply` is computed in `uint256` and then explicitly cast to `uint128`. That cast truncates instead of reverting. If a market’s total tracked balance is very small, reward-per-share becomes enormous; with a 1 wei supply, only about 340 CANTO of rewards in one update step is enough to overflow the cast. A dust depositor can create exactly that condition by being the sole supplier for a while, then triggering an update.
- Impact: the shared accumulator wraps and reward accounting for that market becomes permanently wrong. The practical result is that a large portion of emitted rewards becomes unclaimable or severely underpaid, letting an attacker grief the reward stream for that market with a tiny deposit.

## Catch-up accounting can grow until a market becomes unserviceable
- Location: [LendingLedger.sol](/Users/augstar/open-evmbench/audit_sources/2024-01-canto/src/LendingLedger.sol:56) : `update_market`
- Mechanism: `update_market` advances from `lastRewardBlock` to `block.number` in a `while` loop with no hard cap, performing an external gauge-weight write on each iteration. The work therefore grows linearly with the number of missed epochs. Since both `sync_ledger` and `claim` call `update_market`, a sufficiently stale market eventually requires too much gas to catch up in one transaction.
- Impact: a quiet whitelisted market can become impossible to update or claim from once enough epochs have elapsed. At that point users are effectively locked out of syncing balances and collecting accrued CANTO for that market.

