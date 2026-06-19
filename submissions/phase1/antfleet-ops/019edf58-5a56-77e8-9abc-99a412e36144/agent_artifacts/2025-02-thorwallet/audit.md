# Audit: 2025-02-thorwallet

## Unbounded TGT merge allows TITN insolvency
- Location: MergeTgt.sol : `onTokenTransfer`
- Mechanism: `onTokenTransfer` calculates `titnOut` via `quoteTitn` and adds it to `claimableTitnPerUser` / `totalTitnClaimable` without ever checking that cumulative TGT merged stays within `TGT_TO_EXCHANGE` (579 M) or that `totalTitnClaimable` stays within the contract's TITN holdings (`TITN_ARB` = 173.7 M). In the first 90 days the rate is `tgtAmount * TITN_ARB / TGT_TO_EXCHANGE`; if holders merge more than 579 M TGT in that window, `totalTitnClaimable` exceeds the 173.7 M TITN actually held by the contract.
- Impact: The contract becomes insolvent — later claimers find `titn.safeTransfer` reverts because the contract is out of TITN. Those users deposited real TGT but can never receive their TITN.

## Owner can drain user-deposited TGT and allocated TITN
- Location: MergeTgt.sol : `withdraw`
- Mechanism: `withdraw(IERC20 token, uint256 amount)` has no restriction on *which* token or *how much* can be withdrawn. It calls `token.safeTransfer(owner(), amount)` for any token, including the TGT users sent via `onTokenTransfer` and the TITN earmarked for user claims.
- Impact: A compromised or malicious owner can steal all user-deposited TGT and all TITN held in the contract, leaving users unable to claim.

## `withdrawRemainingTitn` can be permanently bricked by an arithmetic underflow
- Location: MergeTgt.sol : `withdrawRemainingTitn`
- Mechanism: On the first call after 360 days the contract sets `remainingTitnAfter1Year = titn.balanceOf(address(this))` and `initialTotalClaimable = totalTitnClaimable`. It then computes `unclaimedTitn = remainingTitnAfter1Year - initialTotalClaimable`. If the TITN balance is below `totalTitnClaimable` (caused by owner withdrawals via `withdraw`, or by the unbounded-merge insolvency above), this subtraction underflows and reverts. Because the initialisation is guarded by `if (remainingTitnAfter1Year == 0)`, the first failed call does **not** persist the values, so the next caller hits the same underflow — the function is bricked indefinitely. Meanwhile `claimTitn` already reverts after 360 days, so users with outstanding `claimableTitn` are permanently locked out.
- Impact: All users who did not claim before the 360-day mark permanently lose their claimable TITN.

## Transfer lock in Titn is bypassable via LayerZero `send` (OFT `_burn`)
- Location: Titn.sol : `transfer` / `transferFrom` / `_validateTransfer`
- Mechanism: The transfer restriction is enforced only in `_validateTransfer`, which is called from the overridden `transfer` and `transferFrom`. The LayerZero OFT `send` path (cross-chain bridging) calls `_debit` → `_burn` internally; `_burn` never touches `transfer`/`transferFrom`, so `_validateTransfer` is never invoked. A `isBridgedTokenHolder` (or any user on Arbitrum where `block.chainid == 42161`) whose local transfers are blocked by `isBridgedTokensTransferLocked` can still call `send` to bridge tokens to another chain, burning them on Arbitrum and minting them on the destination.
- Impact: The "bridged tokens transfer lock" can be circumvented by any token holder who bridges via LayerZero, defeating the restriction's purpose.

## Off-by-one merge window lets users deposit TGT for zero TITN
- Location: MergeTgt.sol : `onTokenTransfer` / `quoteTitn`
- Mechanism: `onTokenTransfer` rejects merges only when `block.timestamp - launchTime > 360 days` (strictly greater). `quoteTitn` returns 0 when `timeSinceLaunch >= 360 days` (the `else` branch). At exactly 360 days after launch, the guard in `onTokenTransfer` passes, `quoteTitn` returns 0, and there is no check that `titnOut > 0`. The user's TGT is accepted and locked in the contract while `claimableTitnPerUser` is credited with 0.
- Impact: A user who merges at exactly the 360-day boundary irrevocably loses their TGT with no TITN compensation.
