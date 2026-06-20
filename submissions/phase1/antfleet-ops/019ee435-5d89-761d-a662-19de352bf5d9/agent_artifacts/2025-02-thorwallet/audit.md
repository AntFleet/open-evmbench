# Audit: 2025-02-thorwallet

I found two genuine security issues.

## Merge claims can become undercollateralized and first-claimer drains the pool
- Location: `contracts/MergeTgt.sol` : `onTokenTransfer`, `claimTitn`, `withdrawRemainingTitn`
- Mechanism: `onTokenTransfer` credits `claimableTitnPerUser[from]` and increments `totalTitnClaimable` without enforcing either `totalTitnClaimable + titnOut <= titn.balanceOf(address(this))` or a cumulative TGT/TITN exchange cap. As a result, the contract can issue more TITN claims than it actually holds. `claimTitn` then pays from the shared live TITN balance, not from per-user reserved escrow. After 360 days, the same overcommitment can also make `withdrawRemainingTitn` revert via `remainingTitnAfter1Year - initialTotalClaimable` underflow.
- Impact: An attacker can transfer TGT after other users have accrued unclaimed TITN, then call `claimTitn` first and consume the remaining TITN backing. Earlier users are left with claimable balances that cannot be paid, while their TGT has already been accepted by the contract. If the overcommitment survives until the post-year withdrawal path, remaining withdrawals can be bricked for all claimants.

## Bridged-token transfer lock can be bypassed through untracked recipients
- Location: `contracts/Titn.sol` : `_validateTransfer`, `_credit`
- Mechanism: The transfer restriction is tracked with `isBridgedTokenHolder[address]`, but `_credit` only marks the direct bridge recipient. The flag is not propagated when bridged tokens move during an unlocked period, or when they move through `transferAllowedContract`, whose outgoing transfers are fully exempt from `_validateTransfer`. On non-Arbitrum chains, a recipient that receives bridged-origin tokens this way remains unmarked, so later lock checks do not apply to them.
- Impact: Bridged tokens that are supposed to remain non-transferable while `isBridgedTokensTransferLocked` is true can be laundered into unmarked addresses. Those addresses can then transfer the tokens freely on non-Arbitrum deployments, defeating the bridged-token lock.

