# Audit: 2025-02-thorwallet

**Owner can arbitrarily withdraw deposited TITN (and TGT)**  
- Location: `MergeTgt.sol:withdraw`  
- Mechanism: The `withdraw` function is callable by `onlyOwner` at any time and performs an unconditional `token.safeTransfer(owner(), amount)` with no checks against `lockedStatus`, `launchTime`, `TITN_ARB`, `totalTitnClaimable`, or whether the contract is still in the merge period.  
- Impact: The contract owner can drain the entire TITN balance (and any TGT held) before or after users have deposited TGT via `onTokenTransfer`, stealing all funds intended for the merge.

**No cap on total claimable TITN vs. contract balance; over-allocation possible**  
- Location: `MergeTgt.sol:onTokenTransfer` (and `quoteTitn`)  
- Mechanism: `onTokenTransfer` unconditionally adds `quoteTitn(amount)` to `claimableTitnPerUser[from]` and `totalTitnClaimable` with no check that the cumulative claimable amount will not exceed `titn.balanceOf(address(this))` (which is fixed at exactly `TITN_ARB` after the single allowed `deposit`). `quoteTitn` returns a positive value for any `tgtAmount` as long as `timeSinceLaunch < 360 days`.  
- Impact: If more than `TGT_TO_EXCHANGE` TGT is sent (or if timing/rounding allows), `totalTitnClaimable` can exceed available TITN; later claims or `withdrawRemainingTitn` will fail or under-pay users.

**Missing launch-time guard in `claimTitn`**  
- Location: `MergeTgt.sol:claimTitn`  
- Mechanism: `claimTitn` only checks `amount <= claimableTitnPerUser[msg.sender]` and `block.timestamp - launchTime >= 360 days`; it has no `require(launchTime > 0)` (unlike `quoteTitn`, `withdrawRemainingTitn`, and `onTokenTransfer`). When `launchTime == 0`, `block.timestamp - 0` is a large value, so the call immediately hits the `TooLateToClaimRemainingTitn` revert.  
- Impact: Users who received claimable TITN before launchTime is set cannot ever claim via the normal path; funds are permanently stuck unless the owner later sets launchTime.

**State inconsistency in `withdrawRemainingTitn` after partial claims**  
- Location: `MergeTgt.sol:withdrawRemainingTitn`  
- Mechanism: The function snapshots `remainingTitnAfter1Year` and `initialTotalClaimable` only on the first call, then computes `userProportionalShare` solely from the user's remaining `claimableTitnPerUser` value. It subtracts only the original `claimableTitn` from `totalTitnClaimable` while adding the full `titnOut` (including share) to `totalTitnClaimed`. Any TITN already claimed normally before the 360-day mark is never accounted for in the snapshot.  
- Impact: Users who still have claimable TITN at the 360-day mark can receive more than their fair share of the remaining pool, or the accounting invariants (`totalTitnClaimed + totalTitnClaimable == TITN_ARB`) can be violated, allowing double-claiming or permanent under-distribution.

**Owner-controlled `transferAllowedContract` can bypass all TITN transfer locks**  
- Location: `Titn.sol:_validateTransfer` and `setTransferAllowedContract`  
- Mechanism: The transfer restriction logic explicitly whitelists both `from != transferAllowedContract` and `to != transferAllowedContract`. The owner can set this address to any contract (including a malicious one) at any time.  
- Impact: The owner (or a compromised owner key) can designate a contract that lets arbitrary addresses move TITN even while `isBridgedTokensTransferLocked == true` and while on Arbitrum or as a bridged holder, completely defeating the intended transfer locks.
