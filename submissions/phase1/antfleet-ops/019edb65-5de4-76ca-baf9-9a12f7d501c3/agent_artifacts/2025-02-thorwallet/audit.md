# Audit: 2025-02-thorwallet

## Owner can withdraw all TITN and rug users
- Location: `MergeTgt.sol` : `withdraw`
- Mechanism: The `withdraw` function is `onlyOwner` and allows transferring any token (including the `titn` token used for user claims) to the owner's address at any time. There is no restriction preventing the owner from draining the TITN deposited for the merge process.
- Impact: The owner can steal all TITN tokens from the contract, making it insolvent and causing users to lose their entire claimable TITN permanently.

## Owner withdrawal can cause permanent denial of service in `withdrawRemainingTitn`
- Location: `MergeTgt.sol` : `withdrawRemainingTitn`
- Mechanism: The function computes `unclaimedTitn = remainingTitnAfter1Year - initialTotalClaimable`. If the owner has previously withdrawn any TITN (via `withdraw`), the contract's TITN balance may fall below `totalTitnClaimable`, causing an underflow revert when the first user calls `withdrawRemainingTitn` after 360 days. This blocks all subsequent claims.
- Impact: After the 360-day mark, no user can claim their remaining TITN, permanently locking all unclaimed funds. The owner can trigger this accidentally or maliciously by withdrawing even a small amount of TITN.

## Transfer restrictions bypass via OFT `send` (internal transfer)
- Location: `Titn.sol` : `transfer`, `transferFrom` (missing `_update` override)
- Mechanism: The transfer restrictions are only enforced in the overridden `transfer` and `transferFrom` functions. Internal transfers, such as those performed by the OFT base contract’s `_debit` during a cross-chain `send`, call `_transfer` directly without passing through the overridden public functions. The `_validateTransfer` check is therefore never invoked, allowing bridged token holders or any user on Arbitrum to bypass the lock by bridging tokens to another chain.
- Impact: The intended transfer restrictions (e.g., locking bridged holders or Arbitrum users) are completely ineffective. Any restricted user can freely move tokens via the LayerZero bridge, defeating the purpose of the lock.

## TITN claims revert on Arbitrum unless MergeTgt is whitelisted
- Location: `Titn.sol` : `_validateTransfer`
- Mechanism: The validation logic explicitly restricts all transfers on Arbitrum (`block.chainid == 42161`) when `isBridgedTokensTransferLocked` is true, unless the sender is the `owner`, the `transferAllowedContract`, or the recipient is the LayerZero endpoint. The `MergeTgt` contract is not whitelisted by default. When `claimTitn` or `withdrawRemainingTitn` calls `titn.safeTransfer`, the `from` is the `MergeTgt` contract, which is not the owner, not the whitelisted contract, and `to` is a user, causing the transfer to revert.
- Impact: On Arbitrum, users cannot claim their TITN at all. Unless the owner explicitly calls `setTransferAllowedContract` with the `MergeTgt` address, all user funds become permanently inaccessible.

## Bridged token holder status can permanently lock MergeTgt contract
- Location: `Titn.sol` : `_credit`
- Mechanism: The `_credit` function marks any address that receives TITN via a bridge as a bridged token holder (`isBridgedTokenHolder[_to] = true`). If TITN is ever bridged to the `MergeTgt` contract address (e.g., by mistake), the contract becomes a bridged holder. Subsequent transfers from it will then be restricted on all chains (since `isBridgedTokenHolder[from]` becomes true), blocking all `safeTransfer` calls from `claimTitn` and `withdrawRemainingTitn`.
- Impact: The `MergeTgt` contract could be rendered unable to distribute TITN, locking all user funds. This can happen if the owner or any third party mistakenly bridges TITN to the contract address.
