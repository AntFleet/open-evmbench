# Audit: 2025-02-thorwallet

## Disproportionate capture of the year-end TITN leftover
- Location: contracts/MergeTgt.sol : withdrawRemainingTitn
- Mechanism: The leftover pool `unclaimedTitn = remainingTitnAfter1Year - initialTotalClaimable` is split with `userProportionalShare = (claimableTitn * unclaimedTitn) / initialTotalClaimable`, where the denominator is only the *still-unclaimed* claims captured at the first post-360-day call. Users who already drew down `claimableTitnPerUser` via `claimTitn` are therefore excluded from the leftover split, and the entire leftover is divided only among whoever still has a non-zero `claimableTitnPerUser`. When little TGT was merged (so `unclaimedTitn` is large) and few claimants remain, the ratio `unclaimedTitn/initialTotalClaimable` is huge: an attacker merges a tiny amount of TGT via `onTokenTransfer`, deliberately never calls `claimTitn`, and after 360 days calls `withdrawRemainingTitn` to scoop a share of the reserve far exceeding their contribution — up to nearly the whole balance if they are the only remaining claimant.
- Impact: A late/minimal participant drains a disproportionate (potentially near-total) share of the unclaimed TITN reserve, while honest users who used `claimTitn` forfeit their leftover entitlement.

## No cap on exchanged TGT causes over-allocation and contract insolvency
- Location: contracts/MergeTgt.sol : onTokenTransfer
- Mechanism: `onTokenTransfer` adds `quoteTitn(amount)` to `claimableTitnPerUser[from]` and `totalTitnClaimable` on every TGT inflow without ever comparing cumulative exchanged TGT against `TGT_TO_EXCHANGE` (579M) or cumulative assigned TITN against the deposited `TITN_ARB` (173.7M). TGT total supply is 1B, so if more than 579M TGT is exchanged during the first 90 days (full-rate window), assigned claimable TITN exceeds the 173.7M actually held. Early users drain the reserve through `claimTitn`; subsequent `claimTitn` calls then revert on `titn.safeTransfer` for lack of balance, and `withdrawRemainingTitn` reverts via underflow of `remainingTitnAfter1Year - initialTotalClaimable` (contract balance is below outstanding claims), which permanently bricks all year-end withdrawals since the snapshot can never be initialized.
- Impact: The protocol becomes insolvent — late claimants cannot retrieve their owed TITN and the entire `withdrawRemainingTitn` path is permanently denial-of-serviced.

## Owner can seize the TITN reserve backing user claims
- Location: contracts/MergeTgt.sol : withdraw
- Mechanism: `withdraw(IERC20 token, uint256 amount)` is gated only by `onlyOwner` and transfers an arbitrary amount of any token — including `titn` — to the owner, with no carve-out for the TITN that backs already-accrued `claimableTitnPerUser`/`totalTitnClaimable`. After users have exchanged TGT and accrued claims via `onTokenTransfer`, the owner can call `withdraw(titn, balance)` and remove the reserve.
- Impact: The owner can unilaterally drain the TITN that users are owed, causing `claimTitn` and `withdrawRemainingTitn` to revert and permanently denying users their claims.

## Transfer lock is bypassable via the OFT bridge path
- Location: contracts/Titn.sol : _validateTransfer (vs. _credit / inherited _debit)
- Mechanism: `_validateTransfer` is only invoked from the overridden `transfer`/`transferFrom`. The LayerZero OFT `send()` flow debits the sender through `_debit → _burn` and credits the destination through `_credit → _mint`, neither of which routes through `transfer`/`transferFrom`, so the lock is never evaluated when bridging. A holder whose transfers are blocked (a `isBridgedTokenHolder`, or any holder on Arbitrum while `isBridgedTokensTransferLocked` is true) can still call `send()` to move tokens cross-chain; on any chain whose `isBridgedTokensTransferLocked` is false they can then transfer or sell the minted tokens freely.
- Impact: A supposedly locked holder can circumvent the transfer restriction by bridging out to an unlocked chain and liquidating, defeating the intended lockup.

