# Audit: 2024-03-neobase
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

### update_market values every historical epoch at the current week's gauge weight
*(consensus, 6 of 6 reports)*
- Location: `src/LendingLedger.sol` : `update_market` (the `epochTime` computation and its use inside the `while (i < block.number)` loop)
- Mechanism: `epochTime = referenceBlockTime + ((block.number - referenceBlockNumber) * averageBlockTime) / 1000` depends only on `block.number`, never on the loop cursor `i`/`epoch`, so it is identical on every iteration and always equals "now." Each back-filled epoch is therefore credited with `gauge_relative_weight_write(_market, epochTime)` at the *current* week's weight instead of the weight that was in effect during the epoch being settled.
- Impact: An attacker who is a depositor in a market and holds (or rents via the 5-year lock) veCANTO can let many low-weight epochs accumulate, vote the gauge's weight up, wait for it to take effect in the current week, then trigger `update_market`/`claim` so the entire backlog is credited at the inflated weight. Because all markets draw from one CANTO balance, this over-allocates to the attacker's market and drains rewards owed to other markets (insolvency for honest claimers). Symmetrically, weight decreases retroactively destroy already-earned rewards.

### Silent `uint128` truncation of `accCantoPerShare` / `secRewardsPerShare`
*(consensus, 5 of 6 reports)*
- Location: `src/LendingLedger.sol` : `update_market` (the two `+=` lines that cast to `uint128`)
- Mechanism: Both accumulators are `uint128`; each increment is computed in `uint256` and explicitly downcast with `uint128(...)`, which in Solidity 0.8.x does *not* revert on overflow — it truncates mod 2^128. The numerator `blockDelta * cantoPerBlock * relWeight` (carrying `1e18`, and `1e36` for the seconds index) scales with `1/marketSupply`, so a tiny `marketSupply` drives the quotient past `2^128`.
- Impact: An attacker who is the sole/first depositor of a freshly whitelisted, funded market deposits `1 wei`, lets blocks elapse, and triggers `update_market`; the stored index wraps to a garbage value, permanently corrupting MasterChef-style accounting for that market (lost claims, reverting claims, or mis-credit for all later depositors). `secRewardsPerShare` truncates for `marketSupply ≲ 294 wei`.
- Reviewer disagreement: one of the five (gpt-5.5 shot 2) flagged only `secRewardsPerShare`; the others cover both accumulators on the same cast.

### `remove_gauge` reads the gauge type *after* zeroing it (computes type `-1`)
*(consensus, 5 of 6 reports)*
- Location: `src/GaugeController.sol` : `remove_gauge` → `_remove_gauge_weight`
- Mechanism: `remove_gauge` executes `gauge_types_[_gauge] = 0;` *before* calling `_remove_gauge_weight`, whose first line `int128 gauge_type = gauge_types_[_gauge] - 1;` then evaluates to `-1`. `_get_sum(-1)` returns `0`, so `new_sum = old_sum_bias - old_weight_bias` becomes `0 - old_weight_bias` and underflows/reverts under 0.8 checked math for any gauge with positive weight; a zero-weight gauge silently writes to phantom type `-1`. (`add_gauge` sets the type before changing weight, and standalone `remove_gauge_weight` does not zero first — confirming this is an ordering defect.)
- Impact: Governance cannot remove any gauge that has received votes — exactly the malicious/obsolete gauges one would want delisted; a voter can keep a gauge unremovable by maintaining any positive weight on it, so it keeps receiving CANTO. On a zero-weight gauge the call "succeeds" but never clears the gauge's bias from its real type's `points_sum`, diluting every other gauge's relative weight.

### Voting power is permanently trapped on removed gauges
*(consensus, 2 of 6 reports)*
- Location: `src/GaugeController.sol` : `vote_for_gauge_weights`
- Mechanism: The early guard `require(_user_weight == 0 || gauge_types_[_gauge_addr] != 0, ...)` is written to permit a weight-0 withdrawal from a removed gauge (per its own comment), but the function later computes `gauge_type = gauge_types_[_gauge_addr] - 1` (`= -1` for a removed gauge) and then `require(gauge_type >= 0, "Gauge not added")`, which always reverts — making the withdrawal path unreachable.
- Impact: After governance removes a gauge, every user who voted for it has `vote_user_power[msg.sender]` permanently inflated and can never reclaim it. A voter who put 100% of their power on a since-removed gauge is locked out of voting entirely (`"Used too much power"`); smaller voters are permanently capped below 100% allocatable power.

### VotingEscrow decay loops are shorter than the lock duration (255 vs ~260 weeks)
*(consensus, 2 of 6 reports)*
- Location: `src/VotingEscrow.sol` : `_checkpoint` / `_supplyAt`
- Mechanism: Locks last `1825 days` (~260 weeks) but both weekly decay loops are capped at 255 iterations. If more than 255 weeks elapse without a checkpoint, the loops stop before reaching the target timestamp; `_supplyAt` returns supply from the 255-week point rather than the requested time, and `_checkpoint` can write a global point whose timestamp is still stale.
- Impact: After long inactivity `totalSupply()`/`totalSupplyAt()` can report inflated/stale voting supply even when locks should have mostly decayed, and a later checkpoint writes corrupted global history — distorting governance/quorum logic and the `GaugeController` weighting that consumes it.

### LiquidityGauge mints shares from the requested amount, not the received amount
*(consensus, 2 of 6 reports)*
- Location: `src/LiquidityGauge.sol` : `depositUnderlying` (/ `withdrawUnderlying`)
- Mechanism: `depositUnderlying` calls `safeTransferFrom(_user, address(this), _amount)` and then mints exactly `_amount` gauge tokens with no check of the actual balance delta; `withdrawUnderlying` later burns `_amount` and transfers `_amount` underlying back. For fee-on-transfer / deflationary / rebasing tokens the gauge receives less than `_amount` while minting full shares.
- Impact: If governance enables a gauge for such a token, an attacker deposits and is credited full gauge shares while the contract receives less, then withdraws full value — draining gauge liquidity or leaving later withdrawals insolvent.

## Minority findings

### `update_market` advances `lastRewardBlock` past unfunded epochs, permanently losing those rewards
*(minority, 1 of 6 reports)*
- Location: `src/LendingLedger.sol` : `update_market` (the `while` loop and `market.lastRewardBlock = uint64(block.number)`); `public`
- Mechanism: The loop runs from `lastRewardBlock` to `block.number` regardless of whether `cantoPerBlock[epoch]` is set. For an epoch still at `0`, the `accCantoPerShare` increment is `0` but `lastRewardBlock` is unconditionally advanced; if governance later funds that now-past epoch via `setRewards`, `update_market` never revisits those blocks.
- Impact: Anyone can call `update_market(market)` right after an epoch boundary, before governance funds the new epoch, permanently zeroing that epoch's rewards for the market's stakers (griefing). The design implicitly requires `setRewards` to be front-run ahead of every epoch.

### Current (unfinished) epoch can be finalized / claimed early
*(minority, 1 of 6 reports)*
- Location: `src/LendingLedger.sol` : `update_market` / `claim` (`public`)
- Mechanism: `update_market` advances `market.lastRewardBlock` all the way to `block.number`, including the current unfinished epoch, despite the comment that claims should only cover finished epochs. Since `update_market` is public and `claim` calls it, anyone can lock in the current `cantoPerBlock` and gauge weight for the elapsed current-epoch blocks before the epoch is finalized; if rewards are later corrected for that epoch, already-finalized blocks are not recomputed.
- Impact: Anyone can grief a whitelisted market by updating it before governance sets/corrects rewards for the current epoch, permanently skipping those blocks or accounting them at a stale rate.

### `withdraw` checkpoints with `delegated = 0` while the stored lock keeps incoming delegations
*(minority, 1 of 6 reports)* *(conflicting reviews: 2 of 6 reports defended this code path)*
- Location: `src/VotingEscrow.sol` : `withdraw`
- Mechanism: `withdraw` stores `locked[msg.sender] = newLocked` with `delegated = old.delegated - ownAmount` (i.e. any *incoming* delegations remain), then sets the in-memory `newLocked.delegated = 0` and passes that to `_checkpoint`. With `unlockOverride` enabled, withdrawal is permitted while `locked_.end > block.timestamp`, so `_checkpoint` computes `userOldPoint` from `delegated = own + incoming` and `userNewPoint` from `delegated = 0`, removing `own + incoming` voting power from the global point and cancelling the full scheduled slope change even though the incoming delegators' CANTO is still locked.
- Impact: A delegatee who withdraws (with the `unlockOverride` emergency switch) destroys their delegators' still-locked voting power and under-counts global `totalSupply`; later undelegation/expiry of those positions double-subtracts, driving global bias/slope negative (clamped to 0) and corrupting `totalSupply`/`balanceOfAt` that `GaugeController` consumes.
- Reviewer disagreement: two reports treat the delegation branches in `increaseAmount`/`withdraw` as dead/unreachable code because no `delegate()` entrypoint is exposed in the source.

### `setBlockTimeParameters` accepts values that brick `update_market`
*(minority, 1 of 6 reports)*
- Location: `src/LendingLedger.sol` : `setBlockTimeParameters` (interacting with the `epochTime` computation in `update_market`)
- Mechanism: The setter writes `averageBlockTime`, `referenceBlockTime`, `referenceBlockNumber` with no validation. `update_market` computes `epochTime = referenceBlockTime + ((block.number - referenceBlockNumber) * averageBlockTime) / 1000`. A `referenceBlockNumber > block.number` underflows and reverts; a sufficiently large `averageBlockTime` overflows the multiplication and reverts.
- Impact: A single bad (governance-set) parameter makes `update_market` revert, and since `sync_ledger` and `claim` invoke it, every deposit, withdrawal, and claim across all whitelisted markets is bricked until corrected.

### Gauge shares can be burned without releasing the underlying
*(minority, 1 of 6 reports)*
- Location: `src/LiquidityGauge.sol` : `ERC20Burnable` inheritance / `_afterTokenTransfer`
- Mechanism: The gauge inherits public `burn` and `burnFrom`. Burning triggers `_afterTokenTransfer`, which calls `sync_ledger` with a negative delta and reduces both the user's ledger balance and the total market balance — but no underlying token is transferred out, so the underlying stays stranded while accounting supply shrinks.
- Impact: A holder can permanently desync underlying assets from gauge supply and shrink the reward denominator, potentially boosting CANTO rewards on a remaining balance; an approved spender can also destroy a user's withdrawal claim via `burnFrom`.

---

*Reconciliation: 27 raw findings across the 6 reports → 11 distinct findings (6 consensus, 5 minority); all 27 raw findings map onto these 11, none dropped.*

