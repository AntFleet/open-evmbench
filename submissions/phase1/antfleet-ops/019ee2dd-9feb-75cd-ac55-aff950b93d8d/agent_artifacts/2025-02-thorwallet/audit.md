# Audit: 2025-02-thorwallet

 ## Owner can drain all user deposits and claim reserves (Critical)
- **Location:** `MergeTgt.sol` : `withdraw`
- **Mechanism:** The `withdraw` function is `onlyOwner` and transfers any ERC20 held by the contract to the owner without restrictions, balance checks, or timelocks. This includes TGT deposited by users through `onTokenTransfer` and TITN deposited for claims.
- **Impact:** A malicious or compromised owner can rug-pull every user deposit and all TITN reserves, leaving claimers unable to withdraw anything.

## Unbounded TGT exchange can over-obligate TITN reserves (High)
- **Location:** `MergeTgt.sol` : `onTokenTransfer`
- **Mechanism:** `onTokenTransfer` increases `claimableTitnPerUser[from]` and `totalTitnClaimable` by `quoteTitn(amount)` without enforcing a cap on the total TGT accepted or verifying that the resulting obligations do not exceed `TITN_ARB` / the contract’s TITN balance.
- **Impact:** If more than `TGT_TO_EXCHANGE` TGT is sent (e.g., by a whale or if TGT has an inflated/uncapped supply), the contract records claim obligations larger than its TITN reserves, causing insolvency and reverting later claims.

## TITN transfer lock can brick legitimate MergeTgt claims (High)
- **Location:** `Titn.sol` : `_validateTransfer` ; `MergeTgt.sol` : `claimTitn`, `withdrawRemainingTitn`
- **Mechanism:** `Titn` reverts `transfer`/`transferFrom` while `isBridgedTokensTransferLocked` is true unless the sender is the owner, the configured `transferAllowedContract`, or the LZ endpoint. `MergeTgt` is none of these by default, so `titn.safeTransfer(msg.sender, ...)` in the claim functions will revert unless the Titn owner explicitly whitelists the merge contract.
- **Impact:** Claims can be permanently denied even though the MergeTgt contract records valid claimable balances, effectively locking users’ TITN in the contract (while the owner can still drain it via `withdraw`).

## Bridging can bypass the TITN transfer lock (Medium)
- **Location:** `Titn.sol` : `_validateTransfer`, `_credit` (inherited OFT `_debit`)
- **Mechanism:** `_validateTransfer` only overrides `transfer` and `transferFrom`. The inherited LayerZero OFT `send` path calls `_debit`, which burns tokens and does not invoke `_validateTransfer`. Consequently, a bridged token holder can bridge out tokens even when local transfers are supposedly locked.
- **Impact:** A user subject to the bridged-holder freeze can still move value cross-chain by burning TITN, undermining the lock’s purpose.

## Depositing TGT at exactly 360 days yields zero TITN and traps TGT (Medium)
- **Location:** `MergeTgt.sol` : `onTokenTransfer`, `quoteTitn`
- **Mechanism:** `onTokenTransfer` reverts only when `block.timestamp - launchTime > 360 days`, but `quoteTitn` returns `0` when `timeSinceLaunch == 360 days` (the linear-decay branch has `remainingtime == 0`). At that exact boundary the contract still accepts TGT and credits zero claimable TITN.
- **Impact:** A user who deposits TGT at the 360-day boundary receives no TITN in exchange and has no way to reclaim the TGT; the owner can later withdraw it.

## Remaining-TITN bonus snapshot is manipulable by the owner (Medium)
- **Location:** `MergeTgt.sol` : `withdrawRemainingTitn`
- **Mechanism:** `remainingTitnAfter1Year` and `initialTotalClaimable` are captured on the first `withdrawRemainingTitn` call after 360 days, not at a fixed protocol-defined time. Because the owner can call `withdraw` at any time to remove TITN, the owner can drain the TITN balance before the first remaining claim, causing the snapshot to capture a reduced (or zero) remaining pool.
- **Impact:** Users’ proportional share of remaining TITN can be reduced or eliminated after the merge period, while the owner retains the withdrawn funds.
