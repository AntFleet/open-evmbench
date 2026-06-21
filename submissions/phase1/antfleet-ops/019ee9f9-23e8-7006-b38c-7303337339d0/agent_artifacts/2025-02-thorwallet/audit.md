# Audit: 2025-02-thorwallet

# Security Audit Report: MergeTgt & Titn

---

## Unbounded TGT intake causes TITN insolvency

- **Location:** `MergeTgt.sol` : `onTokenTransfer`
- **Mechanism:** The contract defines `TGT_TO_EXCHANGE` (579M TGT) and `TITN_ARB` (173.7M TITN) as the intended 1:1 pool sizing, and `quoteTitn` prices swaps off that ratio. However, `onTokenTransfer` never tracks cumulative TGT received or enforces a ceiling on total intake. Any number of users can keep sending TGT until the contract is drained of TITN. In the worst case (all TGT deposited in the first 90 days at the maximum rate), liability reaches `TITN_ARB` only after exactly `TGT_TO_EXCHANGE` TGT — but every additional TGT beyond that still mints a positive `titnOut` and increments `claimableTitnPerUser` / `totalTitnClaimable` with no solvency check.
- **Impact:** Once cumulative TGT exceeds the pool design limit, the contract owes more TITN than it holds. Early `claimTitn` callers get paid; later claimers (or all `withdrawRemainingTitn` callers after year 1) receive reverts on `safeTransfer` or, if the owner has not drained funds, receive a pro-rata haircut they were never told about. An attacker can deliberately over-deposit TGT late in the window to inflate global liabilities and grief/harm other users.

---

## Owner can drain all user-allocated TITN at any time

- **Location:** `MergeTgt.sol` : `withdraw`
- **Mechanism:** `withdraw` is `onlyOwner`, accepts any `IERC20` (including `titn`), any `amount`, with no guardrails against withdrawing TITN that is already credited to users via `claimableTitnPerUser` / `totalTitnClaimable`, and no timelock or role separation. The owner can call this before, during, or after the merge window — including immediately before the first `withdrawRemainingTitn` snapshot.
- **Impact:** The owner can rug all merge participants by pulling TITN that backs outstanding claims. Users with `claimableTitnPerUser > 0` will fail on `claimTitn` or `withdrawRemainingTitn` (`safeTransfer` revert). If the owner withdraws before the first year-1 claim, `remainingTitnAfter1Year` snapshots a depleted balance, permanently shrinking every user's proportional bonus in `withdrawRemainingTitn`.

---

## Insolvency permanently bricks year-1 claims (underflow / failed transfers)

- **Location:** `MergeTgt.sol` : `withdrawRemainingTitn`
- **Mechanism:** After 360 days, `claimTitn` is blocked (`>= 360 days`), so `withdrawRemainingTitn` is the only exit. That function snapshots `remainingTitnAfter1Year = titn.balanceOf(this)` on the first call and computes `unclaimedTitn = remainingTitnAfter1Year - initialTotalClaimable`. If early `claimTitn` withdrawals, owner `withdraw` calls, or over-subscription (finding 1) have reduced the live balance below `initialTotalClaimable`, this subtraction **reverts in 0.8.x** (underflow). Even when it does not underflow, the math promises `initialTotalClaimable + unclaimedTitn = remainingTitnAfter1Year` total TITN across all users, but there is no per-call balance check — the last users hit `safeTransfer` failures once the pool is empty.
- **Impact:** Users who did not claim before year 1 can be permanently unable to retrieve TITN: `claimTitn` reverts as too late, `withdrawRemainingTitn` reverts on underflow or insufficient balance. Funds are effectively frozen unless the owner voluntarily re-deposits TITN.

---

## First caller sets global snapshot — manipulable via balance changes

- **Location:** `MergeTgt.sol` : `withdrawRemainingTitn`
- **Mechanism:** `remainingTitnAfter1Year` and `initialTotalClaimable` are initialized lazily on the **first** `withdrawRemainingTitn` call, using whatever `titn.balanceOf(address(this))` and `totalTitnClaimable` happen to be at that block. Any TITN sent directly to the contract (accidental transfer, airdrop, or owner re-deposit) inflates `unclaimedTitn` and therefore every user's `userProportionalShare`. Conversely, any balance reduction before that snapshot (owner `withdraw`, early `claimTitn` race) deflates or bricks the pool (finding 3).
- **Impact:** A user (or the owner) who controls the timing of the first post-year-1 claim can influence the size of the bonus pool for all participants. Combined with the unrestricted owner `withdraw`, the owner can extract TITN and then let an accomplice be first caller to lock in a depleted snapshot, denying the proportional bonus to everyone else.

---

## Titn transfer restrictions bypassed via LayerZero OFT bridge (`send`)

- **Location:** `Titn.sol` : `transfer` / `transferFrom` (missing hook on internal transfer path)
- **Mechanism:** Transfer policy is enforced only in the public `transfer` and `transferFrom` overrides via `_validateTransfer`. LayerZero `OFT` outbound bridging does **not** use those entrypoints — it debits via internal `_debit` → `_burn` / `_update`. That internal path never calls `_validateTransfer`. Inbound bridging already bypasses checks through `_credit` → `_mint` (by design). So when `isBridgedTokensTransferLocked == true`, a holder can still invoke `OFT.send(...)` to bridge TITN off-chain/off-Arbitrum without ever hitting the lock.
- **Impact:** Any transfer lock intended to keep TITN immobile pre-launch (or keep bridged supply inside the merge pipeline via `transferAllowedContract`) can be circumvented by bridging out. Users can exit restrictions early, breaking tokenomics assumptions and potentially dumping before the merge completes.

---

## Arbitrum-wide transfer lock blocks all non-exempt holders when locked

- **Location:** `Titn.sol` : `_validateTransfer`
- **Mechanism:** When `isBridgedTokensTransferLocked` is true, the condition `(isBridgedTokenHolder[from] || block.chainid == arbitrumChainId)` is true for **every** address on Arbitrum (chain id 42161), not only bridged recipients. The only unrestricted paths are `from == owner()`, `from == transferAllowedContract`, `to == transferAllowedContract`, or `to == lzEndpoint`. Constructor `_mint(msg.sender, initialMintAmount)` does **not** mark `msg.sender` as `isBridgedTokenHolder`, but on Arbitrum the chain-id clause still blocks them unless they are `owner()` or `transferAllowedContract`.
- **Impact:** If deployer ≠ `owner`, the entire initial Arbitrum supply is non-transferable while the lock is on — including to the merge contract unless it is explicitly set as `transferAllowedContract`. Misconfiguration bricks the merge deposit/claim flow. This is a deployment/ops footgun with direct fund-flow impact, not just a UX issue.

---

## `claimTitn` ignores `lockedStatus` while `onTokenTransfer` respects it

- **Location:** `MergeTgt.sol` : `claimTitn` vs `onTokenTransfer`
- **Mechanism:** `onTokenTransfer` reverts when `lockedStatus == Locked`. `claimTitn` has no `lockedStatus` check. The owner can flip to `Locked` mid-merge and stop new TGT deposits while TITN continues to flow out via `claimTitn`.
- **Impact:** If `Locked` is meant to freeze the entire merge, the owner (or anyone triggering a pause) only achieves a one-way halt — existing claimers drain TITN while new depositors are blocked. Asymmetric pause can be abused to let insiders claim out while outsiders cannot enter, or to accelerate TITN depletion during an incident.

---

## TGT deposited to merge is irrecoverable by users; only owner can withdraw

- **Location:** `MergeTgt.sol` : `onTokenTransfer` + `withdraw`
- **Mechanism:** Users send TGT via `transferAndCall` with no user-facing redemption path. The only TGT exit is `withdraw`, which is `onlyOwner` and unrestricted. There is no user refund even if `quoteTitn` returns 0 (e.g., at `timeSinceLaunch >= 360 days` but before the `> 360 days` guard in `onTokenTransfer` fires, or simply due to the decaying rate).
- **Impact:** Users can permanently lose TGT with zero or negligible TITN credit (donation/griefing at end of window). A malicious or compromised owner can seize all accumulated TGT at any time. This is a centralization/trust risk with concrete user-fund loss paths.

---

## `withdrawRemainingTitn` allows only one claim per user — unclaimed early `claimTitn` balance forfeits bonus accounting

- **Location:** `MergeTgt.sol` : `withdrawRemainingTitn` / `claimTitn`
- **Mechanism:** Users who partially claimed via `claimTitn` before year 1 reduce `claimableTitnPerUser` but keep a non-zero `claimedTitnPerUser`. After year 1 they can only call `withdrawRemainingTitn` once (balance zeroed). The proportional bonus in `withdrawRemainingTitn` is computed only on the **remaining** `claimableTitn`, not on total historical entitlement. Users who fully early-claimed get no bonus; users who waited get `claimable + proportionalShare`. This is likely intentional tokenomics, but the early-claim path has strictly worse economics with no on-chain warning.
- **Impact:** Not a pure exploit, but users who call `claimTitn` even once before year 1 permanently forfeit the `unclaimedTitn` bonus pool share on the portion they already took. An attacker can social-engineer or front-run users into early partial claims to lock them out of the better year-1 settlement. **Severity: Medium (economic griefing).**

---

## Trust assumption: malicious/compromised `tgt` token can inflate claims

- **Location:** `MergeTgt.sol` : `onTokenTransfer`
- **Mechanism:** The callback trusts that `msg.sender == address(tgt)` implies a real TGT transfer of `amount` occurred. It does not verify `tgt.balanceOf(address(this))` increased by `amount`. A non-standard or malicious `tgt` contract could invoke `onTokenTransfer` without transferring tokens.
- **Impact:** If `tgt` is upgradeable or malicious, unlimited `claimableTitnPerUser` can be minted without TGT collateral, draining all TITN. **Low if `tgt` is a known immutable token; Critical if `tgt` is not fully trusted.**

---

# Summary Table

| Severity | Finding |
|----------|---------|
| **Critical** | Unbounded TGT intake → TITN insolvency |
| **Critical** | Owner unrestricted `withdraw` of TITN/TGT |
| **High** | Year-1 claims bricked on insolvency (underflow / empty pool) |
| **High** | Titn lock bypass via OFT `send` (missing `_update` hook) |
| **High** | Snapshot manipulation on first `withdrawRemainingTitn` |
| **Medium** | Asymmetric pause (`claimTitn` ignores `lockedStatus`) |
| **Medium** | Arbitrum blanket lock misconfiguration bricks transfers |
| **Medium** | TGT irrecoverable by users (owner-only `withdraw`) |
| **Low–Medium** | Economic griefing via early `claimTitn` vs year-1 bonus |
| **Low** (trust) | Malicious `tgt` can fake callbacks |

---

# Recommended Fixes (guidance only)

1. Track `totalTgtReceived` and revert in `onTokenTransfer` when it would exceed `TGT_TO_EXCHANGE`.
2. Restrict `withdraw` on `titn` (and possibly `tgt`) — e.g., only withdraw excess above `totalTitnClaimable + reserved amounts`, or use a timelocked multisig.
3. In `Titn`, override `_update` (OZ v5) or `_beforeTokenTransfer` / internal `_transfer` to call `_validateTransfer` on all debits, including OFT `send`.
4. Add explicit balance sufficiency checks before updating accounting in `claimTitn` / `withdrawRemainingTitn`.
5. Initialize `remainingTitnAfter1Year` / `initialTotalClaimable` automatically at `launchTime + 360 days` (keeper or permissionless setter) instead of on first user claim.
6. Align `lockedStatus` checks across `claimTitn` and `onTokenTransfer` if a full pause is intended.

I can go deeper on any finding (e.g., a numerical insolvency scenario or the exact OFT `_update` override) if you want that next.

