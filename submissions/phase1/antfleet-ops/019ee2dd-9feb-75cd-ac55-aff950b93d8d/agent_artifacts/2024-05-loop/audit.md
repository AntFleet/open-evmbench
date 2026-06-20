# Audit: 2024-05-loop

 ## Token Claims Sweep the Entire Contract ETH Balance
- Location: `src/PrelaunchPoints.sol` : `_claim`
- Mechanism: In the non-ETH claim path, after swapping user tokens for ETH via `_fillQuote`, the contract deposits `address(this).balance` into `lpETH` and credits the full amount to the claimer (`_receiver`). Because the contract has a payable `receive()` function that accepts ETH without updating any accounting, any ETH sitting in the contract—whether from accidental direct transfers, `selfdestruct`, or leftover swap proceeds—is deposited as lpETH for the token claimer instead of only the ETH produced by that user's swap.
- Impact: Any user with a non-zero token balance can claim lpETH for the entire ETH balance of the contract, stealing ETH sent directly to the contract by others. This breaks the separation between ETH-backed stakes and token-backed claims.

## Raw ERC20 `approve` in `_fillQuote` Breaks Non-Standard Tokens
- Location: `src/PrelaunchPoints.sol` : `_fillQuote`
- Mechanism: The function uses `require(_sellToken.approve(exchangeProxy, _amount))` instead of OpenZeppelin's `SafeERC20.forceApprove`. Tokens that do not return a boolean from `approve` (e.g., some widely deployed stablecoin implementations) cause the call to revert in Solidity 0.8 because the `IERC20` interface declares a `bool` return value. Additionally, any unspent allowance is never reset, which can cause later approvals to fail for tokens that require allowance to be zero before a new non-zero approval is granted.
- Impact: Claims for non-standard ERC20 tokens can be permanently denied, locking users' token deposits in the contract.

## UniswapV3 Swap Validation Allows `recipient == address(0)`
- Location: `src/PrelaunchPoints.sol` : `_validateData`
- Mechanism: For `Exchange.UniswapV3`, the recipient check is `if (recipient != address(this) && recipient != address(0))`. The underlying 0x `sellTokenForEthToUniswapV3` call sends the output ETH to the specified `recipient`; when that recipient is `address(0)`, the swapped ETH is burned/lost instead of arriving at the `PrelaunchPoints` contract.
- Impact: A user—or a compromised/malicious front-end supplying the 0x calldata—can pass `recipient = address(0)`, causing the user's swapped ETH to be lost and the corresponding lpETH claim to fail or be under-collateralized.

## Fee-On-Transfer Tokens Create Accounting Mismatch
- Location: `src/PrelaunchPoints.sol` : `_processLock`
- Mechanism: When locking a token, the contract records the full requested `_amount` in `balances[_receiver][_token]` without verifying the post-transfer balance. If the token deducts a fee on transfer, the contract actually receives less than `_amount`.
- Impact: If such a token is ever allowed, subsequent claims will attempt to swap the recorded balance that exceeds the contract's actual holdings, causing the `_fillQuote` swap to fail and the user to be unable to claim lpETH.
