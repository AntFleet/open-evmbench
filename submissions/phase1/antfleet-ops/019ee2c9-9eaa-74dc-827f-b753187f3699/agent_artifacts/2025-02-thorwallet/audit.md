# Audit: 2025-02-thorwallet

## Unbounded TGT intake makes the merge insolvent
- Location: `contracts/MergeTgt.sol` : `onTokenTransfer`, `quoteTitn`, `claimTitn`
- Mechanism: `onTokenTransfer` credits `claimableTitnPerUser[from]` and increases `totalTitnClaimable` from `quoteTitn(amount)` for every incoming TGT, but never enforces that cumulative deposits stay within `TGT_TO_EXCHANGE` or that cumulative TITN liabilities stay within the funded `TITN_ARB` reserve. In the first 90 days, the formula is calibrated so exactly `TGT_TO_EXCHANGE` maps to exactly `TITN_ARB`; any additional accepted TGT creates more claimable TITN than the contract can ever pay. `claimTitn` trusts that accounting and only discovers the problem when `titn.safeTransfer` runs out of balance.
- Impact: A whale, or simply aggregate participation above the hardcoded cap, can over-allocate the pool. Early claimants drain the fixed TITN reserve, and later users lose their deposited TGT while their TITN claims revert.

## Post-year withdrawal path can be permanently bricked by arithmetic underflow
- Location: `contracts/MergeTgt.sol` : `withdrawRemainingTitn`
- Mechanism: The first post-360-day caller snapshots `remainingTitnAfter1Year = titn.balanceOf(address(this))` and `initialTotalClaimable = totalTitnClaimable`, then computes `unclaimedTitn = remainingTitnAfter1Year - initialTotalClaimable`. That subtraction assumes the contract balance is at least the outstanding claimable amount. If the contract is undercollateralized for any reason, the subtraction underflows and reverts under Solidity 0.8. Because `claimTitn` is disabled after 360 days, there is no alternate redemption path once this state is reached.
- Impact: Once TITN backing falls below outstanding claims, all users with remaining claimable TITN are permanently locked out after year 1.

## Owner can drain the redemption pool and user-deposited assets
- Location: `contracts/MergeTgt.sol` : `withdraw`
- Mechanism: `withdraw` is `onlyOwner` but otherwise unconstrained: it can transfer any token, in any amount, at any time, including the TITN reserve backing user claims and the TGT already deposited by users. The function does not protect `totalTitnClaimable`, does not reserve assets for already-accrued claims, and does not limit withdrawals to accidental tokens.
- Impact: A malicious or compromised owner can rug all TITN owed to users and/or seize all deposited TGT, causing `claimTitn` and `withdrawRemainingTitn` to fail and leaving users with unrecoverable losses.

## TITN transfer lock is bypassable through the OFT bridge path
- Location: `contracts/Titn.sol` : `transfer`, `transferFrom`, `_validateTransfer`
- Mechanism: The transfer restriction is enforced only in the overridden ERC20 entry points `transfer` and `transferFrom`. The inherited OFT outbound bridge flow uses the `send`/`_debit` burn path instead of those wrappers, so `_validateTransfer` is never executed when a locked holder bridges out. Since `isBridgedTokensTransferLocked` is a per-deployment flag, a holder can move tokens off a locked chain to a deployment where transfers are unlocked.
- Impact: Holders subject to the anti-transfer lock can bypass it by bridging to another chain and then transferring or selling there, defeating the lock’s intended market restriction.

## TGT can be accepted for zero TITN at the 360-day boundary
- Location: `contracts/MergeTgt.sol` : `onTokenTransfer`, `quoteTitn`
- Mechanism: `onTokenTransfer` reverts only when `block.timestamp - launchTime > 360 days`, but `quoteTitn` returns `0` when `timeSinceLaunch >= 360 days`. At exactly the 360-day mark, the ERC677 transfer has already moved TGT into the contract, the callback still succeeds, and the user is credited with `0` claimable TITN. There is no `titnOut > 0` check and no refund path for the TGT already transferred.
- Impact: A user transacting at the boundary, or a victim routed there by a malicious frontend/relayer, can irreversibly lose TGT while receiving no redeemable TITN.

