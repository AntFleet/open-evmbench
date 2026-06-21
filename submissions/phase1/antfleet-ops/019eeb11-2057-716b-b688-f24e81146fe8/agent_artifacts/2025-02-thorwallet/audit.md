# Audit: 2025-02-thorwallet
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Uncapped TGT intake over-allocates TITN claims → insolvency & first-come-first-served drain
*(consensus, 6 of 6 reports)*
- Location: `contracts/MergeTgt.sol` : `onTokenTransfer` (with `quoteTitn` / `claimTitn`)
- Mechanism: The contract is funded with a fixed `TITN_ARB` (173.7M) and `onTokenTransfer` does `titnOut = quoteTitn(amount); claimableTitnPerUser[from] += titnOut; totalTitnClaimable += titnOut;` with **no cumulative cap** on TGT accepted and **no check against the actual TITN balance / `TITN_ARB`**. `quoteTitn` prices every deposit at the fixed phase-1 rate (`tgtAmount * TITN_ARB / TGT_TO_EXCHANGE` ≈ 0.3 TITN/TGT). `TGT_TO_EXCHANGE` (579M) is only 57.9% of the 1B TGT supply; the remaining ~421M is freely-transferable ERC-677 and nothing stops it flowing into the merge. Once cumulative TGT exceeds 579M at full rate, `totalTitnClaimable` exceeds the TITN actually held — the solvency invariant `balanceOf(this) >= totalTitnClaimable` breaks.
- Impact: `claimTitn` becomes a race — early callers drain the 173.7M TITN and later valid claims revert on `safeTransfer` for lack of balance. Affected users have already irrevocably surrendered their TGT (only the owner can withdraw TGT), so they lose their TGT for nothing. A whale or coordinated holders can deliberately oversubscribe and front-run to claim first.
- Reviewer disagreement: none — all six reports flag this.

## `withdrawRemainingTitn` underflow permanently bricks the post-1-year distribution
*(consensus, 6 of 6 reports)*
- Location: `contracts/MergeTgt.sol` : `withdrawRemainingTitn` (`uint256 unclaimedTitn = remainingTitnAfter1Year - initialTotalClaimable;`)
- Mechanism: On the first call after 360 days the function snapshots `remainingTitnAfter1Year = titn.balanceOf(this)` and `initialTotalClaimable = totalTitnClaimable`, then subtracts. The subtraction assumes `balance >= totalTitnClaimable`. That invariant is destroyed by (a) the over-allocation above, or (b) the owner pulling TITN via `withdraw`. In either case the checked subtraction underflows and reverts under Solidity ^0.8 — and because the snapshot is taken once and the function reverts before storing it, the path is permanently unusable.
- Impact: Complete, permanent DoS of the entire second-year / bonus proportional distribution for **all** users with claimable TITN; leftover/bonus TITN is stranded with no user recovery route (only `owner().withdraw`).
- Reviewer disagreement: no report disputes the underflow itself; the Opus reports note the share-math is fine *in the solvent case*, i.e. this only manifests once insolvency (Finding 1 or 3) is introduced. *(Surfaced as a standalone finding in 1 report and as the same explicit underflow mechanism in the other 5.)*

## Owner `withdraw` can seize the TITN backing user claims (rug)
*(consensus, 3 of 6 reports)*
- Location: `contracts/MergeTgt.sol` : `withdraw` (`token.safeTransfer(owner(), amount);`)
- Mechanism: `withdraw` is `onlyOwner` but otherwise unconstrained — it transfers an arbitrary `amount` of any token, including the deposited `titn`, with no carve-out protecting the TITN that backs outstanding `claimableTitnPerUser`, no timelock, and no check that `titnBalance - amount >= totalTitnClaimable`.
- Impact: A malicious or compromised owner key can drain the TITN reserves at any point after users have accrued claims, leaving users with non-collectible entries after they have already surrendered their TGT. It also independently triggers the `withdrawRemainingTitn` underflow above, permanently DoSing the year-1 redemption path.
- Reviewer disagreement: none (flagged by all three Opus shots; the gpt-5.5 shots did not address it).

## Bridged-token dust griefing freezes a victim's whole TITN balance
*(consensus, 3 of 6 reports)*
- Location: `contracts/Titn.sol` : `_credit` (with `_validateTransfer`)
- Mechanism: `_credit` runs on every inbound bridge and unconditionally, permanently sets `isBridgedTokenHolder[_to] = true` for the **recipient address** (not per-amount) — a flag the recipient never opted into and that can never be cleared. While `isBridgedTokensTransferLocked` is true, `_validateTransfer` blocks any flagged `from` address from transferring to anything other than `transferAllowedContract` or `lzEndpoint`. OFT bridging can credit an arbitrary recipient.
- Impact: An attacker bridges a dust amount of TITN to any victim, flipping `isBridgedTokenHolder[victim]` to true and freezing the victim's entire balance — including legitimately-held, non-bridged TITN — for the whole duration of the global lock. Cheap, repeatable DoS against arbitrary holders; the flag is only ever lifted for everyone via the owner's global switch.
- Reviewer disagreement: none (Opus shot 1 affirms it; Opus shots 2/3 did not address it).

## Transfer lock bypassable via the OFT `send`/`_debit` (bridge-out) path
*(consensus, 2 of 6 reports)*
- Location: `contracts/Titn.sol` : `_validateTransfer` — only wired into `transfer`/`transferFrom`; the inherited OFT `send`→`_debit`(`_burn`) and `_credit`(`_mint`) paths are not gated, and `_update` is not overridden.
- Mechanism: The lock is enforced only in the ERC-20 `transfer`/`transferFrom` overrides. The native OFT cross-chain `send` debits the holder via `_burn` without ever calling `_validateTransfer`, so a "locked" holder can always move tokens off the current chain. On the destination the lock only persists if that chain's `isBridgedTokensTransferLocked` is also true.
- Impact: A holder locked on Arbitrum (where the lock applies to every holder) can bridge via `send` to any chain whose deployment has the lock disabled (or that the team unlocks first), where the tokens become freely transferable/sellable — defeating the "transfer restricted" guarantee. The Arbitrum lock is only as strong as the weakest chain's configuration. Precondition: a reachable chain with the lock off.
- Reviewer disagreement: Opus shot 1 explicitly argued the lock **cannot** be bypassed to dump bridged tokens — that its flaw is over-restriction (the griefing finding), not under-restriction.

## Minority findings

## TGT deposited at the exact 360-day boundary is taken but credits zero TITN
*(minority, 1 of 6 reports)* *(conflicting reviews: 1 of 6 reports defended this code path)*
- Location: `contracts/MergeTgt.sol` : `onTokenTransfer` (the `block.timestamp - launchTime > 360 days` guard) with `quoteTitn`
- Mechanism: The end-of-merge guard uses strict `>`, so a deposit landing at exactly `launchTime + 360 days` passes the check, but `quoteTitn` returns `0` for `timeSinceLaunch >= 360 days`. `onTokenTransfer` therefore accepts the already-transferred TGT and credits `titnOut == 0`.
- Impact: A user depositing exactly at the 360-day mark forfeits their TGT entirely with no TITN credited and no user-facing recovery (only the owner's `withdraw` can retrieve it). A deterministic loss-of-funds boundary edge.
- Reviewer disagreement: Opus shot 3 examined this same boundary and judged it self-inflicted, not attacker-exploitable.

## Last-minute dust claim sweeps the entire remaining TITN surplus pool
*(minority, 1 of 6 reports)* *(conflicting reviews: 3 of 6 reports defended this code path)*
- Location: `contracts/MergeTgt.sol` : `withdrawRemainingTitn` (with `onTokenTransfer` / `quoteTitn`)
- Mechanism: `withdrawRemainingTitn` distributes all surplus TITN using `claimableTitnPerUser[msg.sender] / initialTotalClaimable`, where `initialTotalClaimable` is only the outstanding unclaimed amount at the first post-year withdrawal — it is not weighted by historical TGT deposited or by the number of participants. Because `onTokenTransfer` stays open until the end of the 360-day window and `quoteTitn` returns a positive amount until then, an attacker can create a small claimable balance shortly before expiry; if other users have already claimed, the attacker becomes the only/dominant remaining claimable account and receives `claimableTitn` + essentially all surplus.
- Impact: An attacker with enough TGT to create any nonzero late claimable balance can drain the entire unallocated TITN surplus after 360 days, provided other users have already claimed or the attacker dominates the remaining claimable denominator.
- Reviewer disagreement: Opus shots 1, 2, and 3 all explicitly defended this exact path — they argue the proportional share-math is solvency-safe (the sum of payouts ≤ the snapshot, floored division only leaves dust and never over-pays) and that a pre-snapshot donation is unprofitable for the donor.

---

*Reconciliation check: 7 distinct findings identified across all 6 input reports (uncapped intake/insolvency, `withdrawRemainingTitn` underflow, owner `withdraw` seizure, bridged-dust freeze griefing, OFT `send` lock bypass, 360-day boundary zero-credit, last-minute surplus sweep); 7 findings emitted (5 consensus + 2 minority). No findings dropped.*

