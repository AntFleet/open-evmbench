# Audit: 2023-12-ethereumcreditguild

# Merged Security Audit Report

Two independent audits (Reviewer A = Claude, Reviewer B = Codex) were reconciled. One finding appears in both reports and is merged below as consensus; three findings appear in only one report.

---

## Consensus findings

## Historical gauge loss spuriously slashes surplus stakers in `getRewards`
*(consensus)*
- **Location:** `src/loan/SurplusGuildMinter.sol` : `getRewards(address user, address term)` — the block that computes `slashed` (first ~10 lines), specifically:
  ```solidity
  bool updateState;
  lastGaugeLoss = GuildToken(guild).lastGaugeLoss(term);
  if (lastGaugeLoss > uint256(userStake.lastGaugeLoss)) {   // <-- userStake not loaded yet
      slashed = true;
  }

  // if the user is not staking, do nothing
  userStake = _stakes[user][term];   // <-- storage load happens AFTER the comparison
  if (userStake.stakeTime == 0)
      return (lastGaugeLoss, userStake, slashed);
  ```
- **Mechanism:** The `slashed` flag should be true only when a *new* loss occurred in the term *after* the user last accounted for one (`term.lastGaugeLoss > userStake.lastGaugeLoss`). But `userStake` is a freshly declared memory struct at the comparison point and is only assigned from `_stakes[user][term]` on the line *after* the comparison. At comparison time `userStake.lastGaugeLoss == 0`, so the condition collapses to `term.lastGaugeLoss > 0`. Consequently `slashed` becomes `true` for **any** term that has *ever* had a loss, regardless of whether the loss happened before the user staked or has already been accounted for — even for a stake opened after the loss that stored the correct `lastGaugeLoss` during `stake()`. The user's own recorded `lastGaugeLoss` is never consulted. When `slashed` is true, the tail of `getRewards` zeroes the user's entire stake (`UserStake({...all 0...})`), emits an `Unstake`, and persists the wiped record — without returning the staked CREDIT (already donated to the term surplus buffer) or the GUILD. The intended code performs the `userStake = _stakes[user][term];` load *before* the `slashed` comparison; reordering it introduces the defect.
- **Impact:** After a term has ever taken a loss (a normal lifetime event), any later surplus staker can be **permissionlessly** slashed by anyone calling `getRewards(victim, term)`, since `getRewards` is `public` and accepts an arbitrary `user`. The victim's recorded CREDIT/GUILD position is zeroed and their CREDIT contribution forfeited to the surplus buffer, with no flash loan or privilege required — the only precondition is that the term has previously reported a loss via `ProfitManager.notifyPnL` (which sets `GuildToken.lastGaugeLoss`). The same wrong branch is reached internally from `stake()`, `unstake()`, and `updateMintRatio()`:
  - `unstake()` does `if (slashed) return;`, so victims can never withdraw — funds are locked/lost.
  - `updateMintRatio()` early-returns, freezing accounting.
  
  This breaks the core first-loss-capital accounting of the surplus-buffer mechanism and causes direct, irrecoverable loss of staker funds.

---

## Additional findings (single-reviewer)

## Rebasing self-transfer inflates shares
*(Reviewer B only)*
- **Location:** `src/tokens/ERC20RebaseDistributor.sol` : `transfer` / `transferFrom`
- **Mechanism:** When `from == to` and the account is rebasing, the code applies both the sender-share decrease path and the receiver-share increase path using the same pre-transfer `rebasingState`. A self-transfer leaves the ERC20 raw balance unchanged, but the final stored `nShares` can increase while `totalRebasingShares` is unchanged or even reduced.
- **Impact:** A rebasing user can inflate their claim on pending rebase rewards and materialize rewards owed to other rebasing users, draining `__unmintedRebaseRewards`. Preconditions: the attacker has a rebasing balance and there are pending/distributed rewards not yet materialized by other rebasing holders.

## First rebasing depositor can capture all credit distributions
*(Reviewer B only)*
- **Location:** `src/tokens/ERC20RebaseDistributor.sol` : `enterRebase` / `distribute`
- **Mechanism:** The rebase share system enforces no minimum seed liquidity or minimum rebasing supply. `distribute()` allocates the entire distribution across the current `totalRebasingShares`, so if the first rebasing account enters with a dust balance, that dust position owns effectively 100% of the rebasing supply.
- **Impact:** If CREDIT rebasing supply is unseeded or negligibly seeded, an attacker can enter rebase with a tiny balance before protocol profits are distributed and capture the full `CreditToken.distribute()` amount intended for CREDIT holders.

## Same-block gauge losses can be bypassed
*(Reviewer B only)*
- **Location:** `src/tokens/GuildToken.sol` : `notifyGaugeLoss` / `applyGaugeLoss` / `_incrementGaugeWeight`
- **Mechanism:** Gauge loss tracking uses `block.timestamp` as the sole loss identifier. When a user with zero weight increments a gauge, `_incrementGaugeWeight()` sets `lastGaugeLossApplied[gauge][user] = block.timestamp`. If another loss for the same gauge is notified later in the same block, `lastGaugeLoss` remains equal to that timestamp, so `applyGaugeLoss()` sees `lastGaugeLossApplied >= lastGaugeLoss` and refuses to slash the user.
- **Impact:** With transaction ordering in a block containing multiple same-gauge loss notifications, a user can add gauge weight between losses and avoid the burn for a later loss in that same block. Preconditions: multiple losses for the same gauge are reported in one block and the attacker can order their gauge increment between them.

---

### Reconciliation notes
- The SurplusGuildMinter `getRewards` ordering bug is the one finding both reviewers independently identified (Reviewer A's sole finding ≡ Reviewer B's finding #3); they are merged above, preserving Reviewer A's code snippet and exploit-path detail (`unstake`/`updateMintRatio` consequences) and Reviewer B's framing that even correctly-stored post-loss stakes are slashed.
- The three rebase/gauge findings were reported only by Reviewer B. Reviewer A explicitly examined `ERC20RebaseDistributor` share/price math and the gauge-loss access paths and judged them sound, but did not raise these as findings — so they are retained as single-reviewer findings rather than consensus.

