# Audit: 2024-01-canto

# Security Audit — Merged Report

Two independent audits (Reviewer A / Claude, Reviewer B / Codex) were reconciled. After comparing root cause **and** code path for every finding, the two reports turned out to cover **disjoint** bugs — even where both touch `LendingLedger.update_market`, they describe different root causes (A: arithmetic/unit correctness inside the loop body; B: unbounded loop length / gas exhaustion). No two findings share the same root cause, so the **Consensus findings** section is empty and every finding is attributed to a single reviewer below.

## Consensus findings

*None.* The two reports do not describe any common bug. Notably, both reviewers inspected the `update_market` epoch loop, but A flags incorrect reward arithmetic within it while B flags unbounded gas growth of the loop itself — distinct root causes, kept separate below rather than force-merged.

## Additional findings (single-reviewer)

## Block-number "epoch" is passed as a UNIX timestamp into the GaugeController
*(Reviewer A only)*
- Location: `src/LendingLedger.sol` : `update_market` (the `gaugeController.gauge_relative_weight_write(_market, epoch)` call in the loop body)
- Mechanism: `update_market` works entirely in **block numbers** (`BLOCK_EPOCH = 100_000`, `epoch = (i / BLOCK_EPOCH) * BLOCK_EPOCH`, `i = block.number`) and passes that block-number-scaled `epoch` as the `_time` argument to the GaugeController, which is entirely **timestamp**-based: `vote_for_gauge_weights` records weights into `points_weight[gauge][next_time]` / `points_sum[next_time]` where `next_time = ((block.timestamp + WEEK) / WEEK) * WEEK` (seconds, ~1.7e9), and `_gauge_relative_weight` looks them up with `t = (_time / WEEK) * WEEK`. A LendingLedger `epoch` is ~1e7 (block numbers) while votes live at keys ~1e9 (timestamps), so `(epoch / 604800) * 604800` indexes a week bucket no vote was ever written to; `points_sum[t].bias == 0` and the function returns `0`.
- Impact: `cantoReward = blockDelta * cantoPerBlock[epoch] * relativeWeight / 1e18` is multiplied by a relative weight that is essentially always `0`, so `accCantoPerShare` never increases for legitimately-voted markets and **CANTO rewards are never distributed** — the core function silently produces nothing, with no caller workaround since the two contracts use incompatible units. Conversely, if a stray vote ever lands on a colliding low bucket, a market could read a weight it was never voted, mis-allocating rewards.

## Reward loop straddles epoch boundaries: `nextEpoch = i + BLOCK_EPOCH` should be `epoch + BLOCK_EPOCH`
*(Reviewer A only)*
- Location: `src/LendingLedger.sol` : `update_market` (`uint256 nextEpoch = i + BLOCK_EPOCH;` then `blockDelta = Math.min(nextEpoch, block.number) - i;`)
- Mechanism: `lastRewardBlock` is set to `uint64(block.number)` both on whitelisting and at the end of every `update_market`, so the loop variable `i` is virtually never aligned to a `BLOCK_EPOCH` boundary. Each iteration computes the current epoch correctly as `epoch = (i / BLOCK_EPOCH) * BLOCK_EPOCH`, but the segment length uses `nextEpoch = i + BLOCK_EPOCH` (a full epoch measured from the unaligned cursor) instead of the true epoch end `epoch + BLOCK_EPOCH`. The `blockDelta` therefore overshoots the current epoch's boundary, and every block in that overshoot is paid with the *current* epoch's `cantoPerBlock[epoch]` and gauge weight even though those blocks belong to a later epoch with a different rate. The cursor stays misaligned forever, so every subsequent epoch is also mis-attributed. Trace (lastRewardBlock=150_000, block.number=320_000): iter1 covers blocks 150k–250k all at `cantoPerBlock[100_000]` (200k–250k should be `cantoPerBlock[200_000]`); iter2 covers 250k–320k all at `cantoPerBlock[200_000]` (300k–320k should be `cantoPerBlock[300_000]`).
- Impact: Whenever governance changes the per-block reward across epochs (the purpose of `setRewards(fromEpoch, toEpoch, amountPerBlock)`), a large fraction of each epoch's blocks are rewarded at the neighbouring epoch's rate. Markets can be systematically over- or under-paid relative to the intended schedule; the error compounds across epochs, is fully deterministic, and is not self-correcting.

## Silent `uint128` truncation of the `accCantoPerShare` accumulator
*(Reviewer A only)*
- Location: `src/LendingLedger.sol` : `update_market` (`market.accCantoPerShare += uint128((cantoReward * 1e18) / marketSupply);`)
- Mechanism: The per-iteration increment `(cantoReward * 1e18) / marketSupply` is computed in `uint256` then explicitly downcast to `uint128`, truncating modulo 2^128 instead of reverting. The increment scales inversely with `marketSupply` (`lendingMarketTotalBalance[_market]`). For a market whose total balance is tiny (e.g. an attacker is the sole depositor with a few wei of cNOTE), the increment can exceed `type(uint128).max` (~3.4e38): with `marketSupply = 1` and `blockDelta` up to 1e5, a per-block reward above ~3.4e15 wei already overflows the cast. The truncated value is then *added* to the shared `accCantoPerShare`, permanently corrupting it.
- Impact: `accCantoPerShare` is a per-market shared value used by every depositor in `claim`/`sync_ledger` (`user.amount * accCantoPerShare / 1e18`). A wrapped accumulator yields arbitrarily wrong pending balances: depositors can be shortchanged, or — if the wrap lands on a large residue — `claim` computes a payout far larger than intended and either drains contract balance for that share or reverts (DoS) for honest depositors. The precondition (low `marketSupply` relative to the reward rate) is reachable by an attacker who deposits a dust amount before others into a freshly-whitelisted market.

## Event/storage desync: `increaseAmount` emits the stale (pre-reset) unlock time
*(Reviewer A only)*
- Location: `src/VotingEscrow.sol` : `increaseAmount` (`uint256 unlockTime = locked_.end;` … `newLocked.end = _floorToWeek(block.timestamp + LOCKTIME);` … `emit Deposit(msg.sender, _value, unlockTime, action, block.timestamp);`)
- Mechanism: `unlockTime` is captured from the *old* lock (`locked_.end`) before the lock is mutated. The function then resets the stored end to `_floorToWeek(block.timestamp + LOCKTIME)` (a fresh 5-year lock), writes that to `locked[msg.sender]`, but emits `Deposit` with the captured *old* `unlockTime`. Storage and the emitted `locktime` field disagree whenever the new end differs from the old one — essentially always, since every `increaseAmount` re-extends to now+LOCKTIME.
- Impact: Off-chain consumers (indexers, UIs, reward/penalty accounting that trusts `Deposit.locktime`) record a lock expiry earlier than the real on-chain expiry. No direct on-chain fund loss, but external systems reconstructing lock state from events will mis-price voting power and mis-time withdrawals; it can also mask that adding 1 wei silently re-locks the entire position for 5 more years.

## Secondary rewards are accrued but have no claim path
*(Reviewer A only)*
- Location: `src/LendingLedger.sol` : `sync_ledger` / `update_market` (`secRewardsPerShare`, `user.secRewardDebt`) — no corresponding claim function exists
- Mechanism: `update_market` accrues `market.secRewardsPerShare` and `sync_ledger` maintains `user.secRewardDebt` on every deposit/withdraw, mirroring the primary-reward bookkeeping. But unlike `accCantoPerShare`, no function anywhere reads `secRewardDebt`/`secRewardsPerShare` to pay a user out (`claim` only handles the CANTO/`accCantoPerShare` side). The `// TODO: Scaling` comment on the `secRewardsPerShare` update confirms the path is unfinished.
- Impact: Any value the protocol intends to distribute through the secondary-reward accounting is permanently inaccessible — tracked in storage but never withdrawable. A latent accounting/locked-value bug that becomes a real loss the moment governance treats `secRewardsPerShare` as a funded reward stream.

## Unbounded reward update loop can permanently DoS a market
*(Reviewer B only)*
- Location: `src/LendingLedger.sol` : `update_market` (while loop over epochs)
- Mechanism: `update_market` iterates from `market.lastRewardBlock` to `block.number` in `BLOCK_EPOCH` chunks with no upper bound. If a whitelisted market is left untouched for enough epochs, the loop can exceed the block gas limit. Since `update_market` is called by `sync_ledger` and `claim`, both deposit/withdrawal accounting and claims for that market become impossible.
- Impact: Any whitelisted market inactive for a long period can become permanently unusable for reward accounting; users may be unable to claim accrued CANTO or update their ledger balances. Precondition: the market remains without successful `update_market` calls for enough block epochs to make the catch-up loop unexecutable within gas limits.

## `setRewards` can be called with an unbounded range and brick governance execution
*(Reviewer B only)*
- Location: `src/LendingLedger.sol` : `setRewards`
- Mechanism: `setRewards` loops from `_fromEpoch` through `_toEpoch` in `BLOCK_EPOCH` increments with no maximum range, writing storage on every iteration, so gas grows linearly with the epoch count. Governance can submit a range too large to execute within the block gas limit.
- Impact: A misconfigured or compromised governance action can make the reward-setting transaction impossible to execute for the intended range, preventing rewards from being configured or corrected over long historical/future windows. Precondition: governance calls `setRewards` with a sufficiently large aligned epoch range.

