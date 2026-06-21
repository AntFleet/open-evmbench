# Audit: 2024-01-canto
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Block-number epoch passed where a UNIX timestamp is expected
*(consensus, 6 of 6 reports)*
- Location: `src/LendingLedger.sol` : `update_market` (the `gaugeController.gauge_relative_weight_write(_market, epoch)` call) → `src/GaugeController.sol` : `_gauge_relative_weight`
- Mechanism: `epoch` is block-number-derived — `BLOCK_EPOCH = 100_000` and `epoch = (i / BLOCK_EPOCH) * BLOCK_EPOCH`, a block number. It is passed straight in as the `_time` argument, but `GaugeController` is entirely timestamp-based: `_gauge_relative_weight` does `t = (_time / WEEK) * WEEK` (`WEEK = 604_800` s) and reads `points_sum[t]` / `points_weight[_gauge][t]`, which are only ever written at `block.timestamp`-derived week buckets (~1.7e9). A block number (~1e6–1e7) floored by `WEEK` lands on 1970-era slots that voting never populates.
- Impact: `gauge_relative_weight_write` returns `0` for every realistic epoch, so `cantoReward` is always `0`, `accCantoPerShare` never grows, and `claim` pays nothing — funded CANTO becomes permanently undistributable/stuck. `update_market` advances `lastRewardBlock` anyway, so skipped blocks cannot be recovered by later checkpoints. If a block-number epoch ever collided with a written week slot, it would read an unrelated gauge's weight and mis-distribute arbitrarily. Triggerable by any caller via `update_market`, `sync_ledger`, or `claim`.
- Reviewer disagreement: none.

## Reward loop is not epoch-aligned (`nextEpoch = i + BLOCK_EPOCH`)
*(consensus, 5 of 6 reports)*
- Location: `src/LendingLedger.sol` : `update_market` (the `while (i < block.number)` loop)
- Mechanism: The loop computes the aligned `epoch = (i / BLOCK_EPOCH) * BLOCK_EPOCH`, but then sets the segment end as `nextEpoch = i + BLOCK_EPOCH` — relative to the current cursor `i`, not to the aligned `epoch`. `lastRewardBlock` (and hence `i`) is set to the raw `block.number` in `whiteListLendingMarket` and at the end of each `update_market`, so it is essentially never aligned to a `BLOCK_EPOCH` boundary. Each segment is therefore shifted by `i mod BLOCK_EPOCH` blocks, and blocks belonging to a later epoch are paid at the *previous* epoch's `cantoPerBlock[epoch]` and relative weight; the misalignment then persists across all later iterations.
- Impact: Whenever governance changes the per-block rate or weight across epochs, the boundary fraction of blocks is paid at the wrong epoch's rate — markets are systematically over- or under-credited by the offset fraction of each rate change. If a later epoch is lowered or zeroed, a market keeps earning the older, higher rate for the misaligned remainder, inflating `accCantoPerShare` above the intended budget; the excess is withdrawn via `claim`, draining CANTO from the shared pot at the expense of other markets. Triggerable by anyone simply by checkpointing after a boundary.
- Reviewer disagreement: none.

## Silent uint128 truncation of reward-per-share accumulators
*(consensus, 5 of 6 reports)*
- Location: `src/LendingLedger.sol` : `update_market` — `market.accCantoPerShare += uint128((cantoReward * 1e18) / marketSupply);` and `market.secRewardsPerShare += uint128((blockDelta * 1e18) / marketSupply);`
- Mechanism: Both accumulators are `uint128` in `MarketInfo`. The per-iteration increment is computed in `uint256` and explicitly cast to `uint128`; Solidity 0.8 does **not** range-check downcasts, so any value ≥ 2¹²⁸ is silently truncated (high bits dropped). With a small `marketSupply` (dust / first-depositor case) and a large `cantoPerBlock` over a `BLOCK_EPOCH`-sized delta, `(cantoReward * 1e18) / marketSupply` easily exceeds 2¹²⁸ (e.g. `marketSupply = 1` wei, `cantoPerBlock = 1e18`, full epoch → increment ≈ 1e41).
- Impact: A sole/early depositor can hold `marketSupply` at dust while a full epoch accrues; the increment wraps mod 2¹²⁸, permanently corrupting that market's index. Every depositor then under- or mis-collects, with the difference locked, and claims can become unrelated to real entitlement, draining the shared CANTO balance. Conversely, if the accumulator is driven near `uint128.max`, a later *checked* `uint128` addition can revert, bricking `claim` and `sync_ledger` for that market until rescue. Reachable by anyone able to trigger `update_market`.
- Reviewer disagreement: none.

## Vote cooldown (`WEIGHT_VOTE_DELAY`) removed from gauge voting
*(consensus, 3 of 6 reports)*
- Location: `src/GaugeController.sol` : `vote_for_gauge_weights`
- Mechanism: Curve's reference implementation guards this function with `require(block.timestamp >= last_user_vote[user][gauge] + WEIGHT_VOTE_DELAY)`. This port still records `last_user_vote[msg.sender][_gauge_addr] = block.timestamp` but never reads it back as a gate, so a user can re-capture and re-apply their VE slope every block. Each vote synchronously updates the gauge's bias for `next_time`, and `gauge_relative_weight_write` reads the live weight whenever any market is checkpointed (permissionlessly via `update_market`).
- Impact: A large veCANTO holder can concentrate full voting power onto whichever market is about to be checkpointed, capture an inflated relative weight for that market's accrual, then immediately shift the same power to the next market and repeat — having one locker's power counted toward multiple gauges' reward periods in the same window, over-allocating CANTO emissions and skewing distribution. (Currently masked by the unit-mismatch finding above, so reports rate it as a genuine removal of the intended anti-manipulation invariant rather than an instant drain.)
- Reviewer disagreement: none.

## Minority findings

## Reward rounds to zero via divide-then-multiply
*(minority, 1 of 6 reports)*
- Location: `src/LendingLedger.sol` : `update_market` — `cantoReward = (blockDelta * cantoPerBlock[epoch] * gauge_relative_weight_write(...)) / 1e18;` followed by `(cantoReward * 1e18) / marketSupply`
- Mechanism: `cantoReward` performs an integer division by `1e18`, and the result is then multiplied back by `1e18` before dividing by `marketSupply`. When `blockDelta * cantoPerBlock[epoch] * relWeight < 1e18` (small relative weight or small per-block rate over a short delta), `cantoReward` floors to `0`, discarding the whole interval's rewards even though the later `* 1e18` would have preserved precision had the ops been multiply-before-divide.
- Impact: Reward dust is silently dropped for low-weight markets / short update intervals, with rounding always favoring the contract (depositors lose, residue locked). An attacker could grind a victim market's accrual toward zero by repeatedly checkpointing it in tiny block deltas.
- Reviewer disagreement: no other report addressed this code path.

## Governance setters and constructors accept the zero address
*(minority, 1 of 6 reports)*
- Location: `src/LendingLedger.sol` : `setGovernance` / constructor; `src/GaugeController.sol` : `setGovernance` / constructor
- Mechanism: `setGovernance(address _governance)` writes the new address with no `!= address(0)` validation, and the constructors take `_governance` / `_gaugeController` / `_votingEscrow` unchecked. `onlyGovernance` is the sole guard for `add_gauge`, `remove_gauge`, `remove_gauge_weight`, `setRewards`, and `whiteListLendingMarket`.
- Impact: A single fat-fingered or front-run `setGovernance(0)` permanently bricks all governance-gated functionality (no rewards configured, no markets whitelisted/removed, no gauges managed) with no recovery path.
- Reviewer disagreement: no other report addressed this code path.

## De-whitelisting a market locks already-earned rewards and can freeze exits
*(minority, 1 of 6 reports)* *(conflicting reviews: 1 of 6 reports defended this code path)*
- Location: `src/LendingLedger.sol` : `update_market` (`require(lendingMarketWhitelist[_market], ...)`) reached via `claim` and `sync_ledger`
- Mechanism: Both `claim` and `sync_ledger` begin by calling `update_market`, whose first statement reverts if the market is not whitelisted. There is no separate path to settle accrued rewards or to record deposits/withdrawals once a market is removed from the whitelist.
- Impact: When governance de-whitelists a market, every `claim` for that market reverts — already-accrued CANTO becomes permanently unclaimable — and every `sync_ledger` call reverts, so if the lending market routes deposit/withdraw through `sync_ledger`, user exits revert too. Governance-triggered availability failure with no migration/escape, punishing honest depositors of a removed (e.g. compromised) market.
- Reviewer disagreement: opus shot 1 treated this same whitelist gate as sound and intended ("`sync_ledger` is gated to whitelisted markets via `update_market`"), i.e. defended the code path rather than flagging the lock-out.

---

*Reconciliation check: 7 distinct findings identified across the 6 input reports (1 unit-mismatch, 1 epoch-alignment, 1 uint128 truncation, 1 vote-cooldown, 1 divide-then-multiply, 1 zero-address, 1 de-whitelist lock-out); 7 findings emitted (4 consensus + 3 minority). Items that every report only ever defended and no report claimed as a finding — `claim`/`VotingEscrow.withdraw` reentrancy (CEI-safe), VotingEscrow int128 `msg.value` casts, unreachable delegation branches, and the unpaid `secRewardsPerShare` feature gap — are intentionally excluded, as no report raised them as findings.*

