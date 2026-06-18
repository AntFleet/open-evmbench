# Audit: 2025-02-thorwallet

I have both reports inline and the task is a careful merge — no codebase access needed. Let me map the findings first, then produce the merged report.

**Mapping:**
- A#1 (uncapped over-allocation, `onTokenTransfer`/`quoteTitn`) ↔ B#1 (uncapped merge claims DoS) → **consensus**
- A#1's impact also explicitly describes the `withdrawRemainingTitn` underflow that B breaks out as B#2 ("`unclaimedTitn = ... -` underflows ... reverts for everyone, permanently bricking the post-year claim path") ↔ B#2 → **consensus** (distinct code path, described by both)
- A#2 (owner `withdraw` pulls TITN) ↔ B#3 → **consensus**
- A#3 (OFT bridge lock bypass), A#4 (decay-boundary zero credit), A#5 (post-year pool concentration) → **Reviewer A only**

---

# Merged Security Audit Report — `MergeTgt.sol` / `Titn.sol`

## Consensus findings

## Uncapped TITN over-allocation enables a first-come-first-served claim drain (DoS)
*(consensus)*
- Location: `contracts/MergeTgt.sol` : `onTokenTransfer` / `quoteTitn` / `claimTitn` (A ~L60–82, L145–158; B ~L65–91, L93–110, L145–157)
- Mechanism: `onTokenTransfer` credits `claimableTitnPerUser[from] += quoteTitn(amount)` and increments `totalTitnClaimable += titnOut` for every incoming TGT, with **no running check** that cumulative allocation stays within the contract's funded TITN balance / `TITN_ARB`. `quoteTitn` computes purely from `tgtAmount` and elapsed time — during the first 90 days `titnOut = tgtAmount * TITN_ARB / TGT_TO_EXCHANGE` — calibrated so that converting exactly `TGT_TO_EXCHANGE` (579M, "57.9% of `MAX_TGT`") yields exactly `TITN_ARB` (173.7M deposited via `deposit`). Nothing on-chain restricts who sends TGT or caps the total converted, and the remaining ~42% of supply may participate. If holders collectively convert **more than `TGT_TO_EXCHANGE`** in the 90-day window, `sum(claimableTitnPerUser) > TITN_ARB =` contract balance. `claimTitn` still trusts the accounting and attempts `titn.safeTransfer`, which only fails once the contract balance is already insufficient.
- Impact: Once allocations exceed deposited TITN the system is insolvent. `claimTitn` becomes first-come-first-served on a fixed 173.7M pool: early claimers' transfers succeed and drain the balance; later legitimate claimants' `safeTransfer` reverts on insufficient balance. A single whale holding ≥ `TGT_TO_EXCHANGE`, or any >57.9% collective participation, triggers it. Preconditions: merge unlocked, `launchTime` set, attacker can push enough TGT through the ERC677 `transferAndCall` callback path. The only restraint (total converted TGT ≤ 57.9%) is a purely social assumption with no enforcement.

## First post-year withdrawal underflows and permanently bricks `withdrawRemainingTitn`
*(consensus)*
- Location: `contracts/MergeTgt.sol` : `withdrawRemainingTitn` (A ~L115–143; B ~L112–143)
- Mechanism: The first caller after 360 days atomically snapshots `remainingTitnAfter1Year = titn.balanceOf(address(this))` and `initialTotalClaimable = totalTitnClaimable`, then computes `unclaimedTitn = remainingTitnAfter1Year - initialTotalClaimable`. This assumes the contract's TITN balance is at least the outstanding claimable amount. If the actual balance is below outstanding claims — due to year-1 over-allocation (finding above), owner withdrawals, fee-on-transfer behavior, or any other balance/accounting mismatch — the subtraction **underflows and reverts under Solidity 0.8**, and the snapshot is already unusable for all future withdrawals.
- Impact: All users with remaining claimable TITN become permanently unable to withdraw after the 360-day period — the post-year claim path is bricked for everyone, not just the triggering caller. Precondition: a post-year withdrawal is attempted while actual TITN balance is lower than `totalTitnClaimable`.

## Owner `withdraw()` can pull claim-reserved TITN and strand user balances
*(consensus)*
- Location: `contracts/MergeTgt.sol` : `withdraw` (A ~L52–55; B ~L53–56)
- Mechanism: `withdraw(IERC20 token, uint256 amount)` is `onlyOwner` but otherwise unconstrained — it can transfer **any** token, including `titn`, in **any** amount, at **any** time, with no accounting check against `totalTitnClaimable` or already-accrued `claimableTitnPerUser`. The contract's TITN balance is the sole backing for all outstanding claim obligations and the post-year distribution; this path removes the backing assets without reducing the recorded liabilities.
- Impact: A malicious or compromised owner key can call `withdraw(titn, titn.balanceOf(this))` and remove all TITN backing user claims, leaving `claimTitn` / `withdrawRemainingTitn` to revert on insufficient balance — a single-key rug of user funds. There is no timelock and no carve-out protecting `totalTitnClaimable`; a withdrawal after the year-1 snapshot also defeats the `withdrawRemainingTitn` distribution. Mitigation: forbid withdrawing TITN below `totalTitnClaimable` (plus the leftover bonus pool) while the merge is live.

## Additional findings (single-reviewer)

## Transfer lock is bypassable through the OFT bridge (`send`/`_debit`) path
*(Reviewer A only)*
- Location: `contracts/Titn.sol` : `_validateTransfer` (~L75–95) and `_credit` (~L104–122); the inherited `OFT.send`/`_debit` is not overridden
- Mechanism: `_validateTransfer` is only invoked from the overridden `transfer`/`transferFrom`. The OFT outbound bridge path (`send` → `_debit` → `_burn`) does **not** route through `transfer`/`transferFrom`, so it never calls `_validateTransfer`. The lock relies on `isBridgedTokensTransferLocked`, an **independent per-chain flag** (each deployment initializes it to `true`, but the owner unlocks each chain separately), plus a blanket `block.chainid == 42161` clause that locks all holders on Arbitrum.
- Impact: A holder whose TITN is locked on Arbitrum (every Arbitrum holder while locked, including merge claimants) can call `send` to bridge tokens to a chain whose `isBridgedTokensTransferLocked` is `false` (e.g. the home chain after its public unlock, while Arbitrum stays locked). On that chain `_validateTransfer` passes and the tokens become freely transferable/sellable, defeating the Arbitrum transfer lock meant to prevent dumping during the merge. Confidence moderate: depends on at least one chain being unlocked while another is locked — the natural deployment configuration.

## TGT is consumed for zero / near-zero TITN at the decay boundary
*(Reviewer A only)*
- Location: `contracts/MergeTgt.sol` : `onTokenTransfer` (~L66) and `quoteTitn` (~L145–158)
- Mechanism: `onTokenTransfer` reverts only when `block.timestamp - launchTime > 360 days`, so it still accepts TGT at and near 360 days. But `quoteTitn` returns `0` for `timeSinceLaunch >= 360 days` and decays linearly to ~0 over the 90→360-day window. The TGT has already been irreversibly transferred into the contract by the ERC677 `transferAndCall` before `onTokenTransfer` runs, and there is no refund/return path for TGT.
- Impact: A user who sends TGT at exactly 360 days (or close to it) gets `claimableTitnPerUser += 0` (or a dust amount) while permanently losing their TGT — a value-loss footgun and a guaranteed total loss at the exact 360-day boundary. Low severity, but a real loss of user funds with no compensating credit.

## Proportional post-year distribution concentrates the entire unallocated pool on whoever participated
*(Reviewer A only)*
- Location: `contracts/MergeTgt.sol` : `withdrawRemainingTitn` (~L115–143)
- Mechanism: After year 1, each remaining claimant receives `claimableTitn + claimableTitn * (remainingTitnAfter1Year - initialTotalClaimable) / initialTotalClaimable`. The second term redistributes **all** never-allocated TITN (`unclaimedTitn`) pro-rata among year-1 participants who did not fully claim via `claimTitn`. The total distributed sums exactly to `remainingTitnAfter1Year` (solvent — not an insolvency bug), but the formula has no floor on participation size: if participation is thin, a single user who converted a trivial amount of TGT and simply waited captures essentially the entire remaining `TITN_ARB`.
- Impact: An actor can intentionally convert a minimal amount of TGT, avoid `claimTitn` during year 1, and after 360 days collect a hugely disproportionate share of the unallocated TITN (up to the whole pool if they are the sole/dominant remaining claimant). "By design" per the proportional rule, but combined with permissionless, uncapped accrual it is an economic griefing/capture vector; a per-user or total cap and explicit handling of the unallocated remainder would mitigate it.

---

### Merge notes
- B's two findings about over-allocation (B#1) and the post-year `withdrawRemainingTitn` underflow (B#2) map to A's single finding #1, which covers both mechanisms (the underflow is described in A#1's *Impact* — "underflows ... reverts for everyone, permanently bricking the post-year claim path"). I split them into two consensus findings to preserve the distinct code paths (`onTokenTransfer`/`claimTitn` vs. `withdrawRemainingTitn`) — both are described by both reviewers.
- The post-year underflow's *Mechanism* preserves B's broader root-cause list (over-allocation, owner withdrawal, fee-on-transfer, any accounting mismatch), which is more specific than A's over-allocation-only framing.
- No findings were introduced that do not appear in at least one source report.

