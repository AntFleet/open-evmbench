# Audit: 2025-02-thorwallet

## Unbounded TGT intake makes TITN claims insolvent
- Location: contracts/MergeTgt.sol : `onTokenTransfer` / `quoteTitn`
- Mechanism: `TGT_TO_EXCHANGE` (579M) is used only as the *denominator* of the exchange rate, never as a cap on how much TGT the contract will accept. `onTokenTransfer` accrues `claimableTitnPerUser[from] += quoteTitn(amount)` for any `amount`, and in the first 90 days `quoteTitn` returns `tgtAmount * TITN_ARB / TGT_TO_EXCHANGE` (a flat 0.3 ratio). Since total TGT supply (MAX_TGT = 1B) far exceeds 579M, the sum of accrued `claimableTitn` can exceed the 173.7M TITN actually deposited. Nothing reconciles outstanding claims against the contract's TITN balance.
- Impact: The contract promises more TITN than it holds. `claimTitn` becomes first-come-first-served: early claimers drain the balance and `titn.safeTransfer` reverts for everyone after the reserve is exhausted. Worse, after 360 days `withdrawRemainingTitn` computes `unclaimedTitn = remainingTitnAfter1Year - initialTotalClaimable`; when total claimable exceeds the balance this subtraction underflows and reverts, permanently bricking that path. Combined with `claimTitn` being disabled at `>= 360 days`, oversubscribed users are permanently locked out of funds.

## Owner can drain TITN owed to users
- Location: contracts/MergeTgt.sol : `withdraw`
- Mechanism: `withdraw(IERC20 token, uint256 amount)` transfers an arbitrary token and amount to `owner()` with no restriction. It does not exclude TITN, nor does it reserve the outstanding `totalTitnClaimable` / `totalTitnClaimable` balance owed to users who have already accrued claims via `onTokenTransfer`.
- Impact: The owner can withdraw the entire TITN reserve after users have swapped their TGT (and after TGT is non-refundably committed), leaving `claimTitn`/`withdrawRemainingTitn` to revert on insufficient balance. Users' TGT is consumed but their TITN claims are unbacked — a one-sided rug, and there is no on-chain refund path for the deposited TGT.

## Transfer lock is bypassable via LayerZero bridge
- Location: contracts/Titn.sol : `_validateTransfer` (and its absence on the OFT debit path)
- Mechanism: The restriction in `_validateTransfer` is only enforced from the overridden `transfer` / `transferFrom`. OFT outbound bridging (`send` → `_debit` → `_burn` via `_update`) does not route through `transfer`/`transferFrom`, so it is never validated. A holder whose tokens are supposed to be frozen (`isBridgedTokensTransferLocked == true`, e.g. an Arbitrum holder or flagged bridged holder) can still call the OFT `send` flow to move tokens cross-chain.
- Impact: The intended transfer lock on bridged/Arbitrum holders is circumventable. A restricted holder bridges tokens to a chain where the lock is not set, then transfers freely, defeating the lockup the protocol relies on.

## Chain-wide freeze of all Arbitrum holders
- Location: contracts/Titn.sol : `_validateTransfer`
- Mechanism: The gate triggers when `isBridgedTokensTransferLocked && (isBridgedTokenHolder[from] || block.chainid == arbitrumChainId)`. On Arbitrum, `block.chainid == arbitrumChainId` is unconditionally true, so the `isBridgedTokenHolder[from]` distinction is irrelevant — every non-exempt holder is restricted, not just bridged ones. Users who legitimately receive TITN (e.g. claimants out of `MergeTgt`) cannot transfer it to any address other than `owner()` or `transferAllowedContract`.
- Impact: While `isBridgedTokensTransferLocked` is true, all ordinary Arbitrum TITN transfers revert. If the owner never flips `setBridgedTokenTransferLocked(false)` (or is unable to), the entire Arbitrum supply held by users is frozen indefinitely. This is a single-key dependency that can render claimed tokens unusable.

## `withdrawRemainingTitn` surplus snapshot is balance-manipulable
- Location: contracts/MergeTgt.sol : `withdrawRemainingTitn`
- Mechanism: On the first post-360-day call, `remainingTitnAfter1Year` is snapshotted from the live `titn.balanceOf(address(this))` and the per-user payout `claimableTitn + (claimableTitn * (remainingTitnAfter1Year - initialTotalClaimable) / initialTotalClaimable)` is computed against that snapshot. The snapshot assumes the balance stays constant across all users' subsequent withdrawals, but the balance can be altered between calls (owner `withdraw`, or any direct TITN movement).
- Impact: If the balance is reduced after the snapshot (e.g. via the owner `withdraw` above, or by an unforeseen transfer), later claimants compute payouts that exceed the remaining balance and their `safeTransfer` reverts — the surplus-distribution math becomes order-dependent and the last claimants are denied funds they were entitled to.

