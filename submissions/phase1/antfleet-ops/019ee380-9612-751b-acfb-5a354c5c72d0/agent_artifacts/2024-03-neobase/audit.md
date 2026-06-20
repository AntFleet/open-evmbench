# Audit: 2024-03-neobase

Below are the genuine security issues I found, ordered roughly by severity. The bulk of the exploitable problems are in `LendingLedger`’s reward accounting.

## Permissionless reward update uses live, manipulable gauge weight for every historic epoch
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: The reward loop walks every unprocessed `BLOCK_EPOCH` from `market.lastRewardBlock` to `block.number`, but `epochTime` is computed **once, outside the per-epoch logic** and is independent of the loop variable `i`/`epoch`. It always evaluates to (approximately) *now*: `referenceBlockTime + ((block.number - referenceBlockNumber) * averageBlockTime)/1000`. It is then fed into `gaugeController.gauge_relative_weight_write(_market, epochTime)`, which both *reads the current weight* and *checkpoints the controller forward to now*. So the relative weight of "today" is applied retroactively to every past epoch being settled. Because `update_market` (via `claim`/`sync_ledger`, or directly) is permissionless, an attacker who holds veCANTO can vote their market’s weight up, trigger `update_market` to bank a large `accCantoPerShare` for all the accumulated blocks at the inflated current weight, then move their votes away.
- Impact: Reward allocation no longer reflects the weight that actually applied during each epoch. A voter can retroactively capture CANTO for epochs in which their gauge had little/no weight, draining the reward budget intended for other markets/epochs.

## CANTO payout is not bounded by funded/allocated rewards
- Location: `src/LendingLedger.sol` : `claim`
- Mechanism: `claim` computes `cantoToSend = user.amount * accCantoPerShare / 1e18 - user.rewardDebt` and sends it straight from the contract’s native balance (`msg.sender.call{value: ...}`). There is no global ledger of how much CANTO has actually been deposited via `receive()` versus how much has been promised by `cantoPerBlock * weight` accrual. `accCantoPerShare` accrues purely from governance’s `setRewards` schedule and gauge weights, with no link to the contract’s real balance.
- Impact: If accrued obligations exceed the CANTO actually funded (over-optimistic `setRewards`, the weight-manipulation above, or any drift), claims become first-come-first-served: early claimers drain the balance and later users’ `claim` calls revert with "Failed to send CANTO", losing rewards they are owed. There is no accounting safeguard preventing the contract from promising more than it holds.

## Silent uint128 truncation in `accCantoPerShare` / `secRewardsPerShare`
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: Both accumulators are `uint128`, and the per-epoch increments are computed in `uint256` and then **explicitly cast** to `uint128`, which truncates (wraps) silently instead of reverting. `secRewardsPerShare += uint128((blockDelta * 1e36) / marketSupply)`: `blockDelta` can be up to `BLOCK_EPOCH = 1e5`, so the numerator reaches ~`1e41`, while `uint128` max is ~`3.4e38`. The same shape applies to `accCantoPerShare` (with `cantoPerBlock` and the 1e18-scaled relative weight in the numerator). When `marketSupply` is small (a market with only a few wei of deposits, easily arranged by being the first/only depositor in a `LiquidityGauge`), the divided result exceeds `2^128`.
- Impact: The accumulator wraps to a wrong (typically much smaller) value, permanently corrupting the per-share accounting for that market. Depending on direction this either bricks reward math or mis-credits users; because `marketSupply` is attacker-influenceable (deposit a tiny amount), it is reachable rather than purely theoretical.

## De-/re-whitelisting strands and skips accrued rewards
- Location: `src/LendingLedger.sol` : `whiteListLendingMarket`
- Mechanism: The function flips `lendingMarketWhitelist[_market]` without first calling `update_market`. When a market is removed (`_isWhiteListed = false`), accrued rewards between `lastRewardBlock` and the current block are never settled, and `update_market` will subsequently revert on the `lendingMarketWhitelist` check, so they can never be settled. When the market is re-whitelisted, the `if (_isWhiteListed)` branch sets `marketInfo[_market].lastRewardBlock = uint64(block.number)`, fast-forwarding past the entire down period.
- Impact: All rewards accrued in the window before removal and during the de-whitelisted period are silently lost to depositors. A governance toggle (even a benign one) destroys user reward entitlements with no migration path.

## `vote_for_gauge_weights` has no vote-change cooldown
- Location: `src/GaugeController.sol` : `vote_for_gauge_weights`
- Mechanism: Curve’s original enforces a `WEIGHT_VOTE_DELAY` (10 days) between weight changes for the same `(user, gauge)` and records `last_user_vote` precisely to enforce it. This port writes `last_user_vote[msg.sender][_gauge_addr] = block.timestamp` but never checks it, so a user can re-point their voting power arbitrarily often within the same epoch.
- Impact: Combined with the live-weight reward issue above, a voter can oscillate weight every block — spiking a gauge’s weight immediately before a `update_market`/reward checkpoint and withdrawing it after — to harvest a disproportionate share of CANTO while bearing the gauge weight for essentially zero time.

---

Notes on things I checked that are **not** exploitable: `claim`/`withdraw` follow checkpoint-before-call ordering (the user’s `rewardDebt`/lock is committed before the external `call`), so the native-token transfers are not reentrancy-exploitable for double payout; the `accCantoPerShare`/relative-weight scaling (extra 1e18 from `gauge_relative_weight` divided back out in `claim`/`sync_ledger`) is internally consistent. The dead `INCREASE_AMOUNT...DELEGATE` branch in `VotingEscrow.increaseAmount` is unreachable because no `delegate()` entry point is included in this code, so I did not count it as a live vulnerability.

