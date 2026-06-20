# Audit: 2026-01-tempo-stablecoin-dex

# StablecoinDEX Security Audit

## Unauthenticated `emergencyWithdraw` drains all contract funds
- Location: `contracts/StablecoinDEX.sol` : `emergencyWithdraw` / `_processWithdrawal`
- Mechanism: `emergencyWithdraw` calls `_processWithdrawal`, which performs `balances[user][token] -= amount` and `totalDeposits[token] -= amount` inside an `unchecked` block and then `safeTransfer`s `amount` to the caller — with **no balance check whatsoever** and no access control. Unlike `withdraw`, there is no `if (balances[msg.sender][token] < amount) revert InsufficientBalance()` guard. Because the subtraction is `unchecked`, a caller with zero (or insufficient) balance simply underflows their balance to a near-`type(uint128).max` value rather than reverting, while the contract unconditionally transfers out the requested tokens.
- Impact: Any external account can call `emergencyWithdraw(token, contractTokenBalance)` and steal the entire pool of any deposited TIP-20 token, draining every liquidity provider's and order maker's funds. Total loss of all assets held by the contract.

## `cancel` has no maker authorization — anyone can cancel any order
- Location: `contracts/StablecoinDEX.sol` : `cancel`
- Mechanism: `cancel(orderId)` only verifies `order.maker != address(0)`; it never checks `msg.sender == order.maker` (note the unused `Unauthorized` error). It then calls `_cancelOrder`, which unlinks the order and credits `refund` back to `order.maker`. The authorization gate that should restrict cancellation to the order's owner is entirely missing.
- Impact: An attacker can cancel arbitrary makers' open orders at will, force-removing their liquidity from the book. This enables order-book manipulation and griefing (e.g., repeatedly cancelling a competitor's or a counterparty's resting orders, removing liquidity right before/after one's own trades, or disrupting MPP settlement routing that depends on the book state). No funds are stolen directly (refund returns to the maker), but the integrity and availability of the order book is fully compromised by any caller.

## Reentrancy in `withdraw` (checks-effects-interactions violation)
- Location: `contracts/StablecoinDEX.sol` : `withdraw`
- Mechanism: `withdraw` checks the balance, then performs `IERC20(token).safeTransfer(msg.sender, amount)` **before** decrementing `balances[msg.sender][token]` and `totalDeposits[token]`. The state update happens after the external token interaction. TIP-20 tokens integrate TIP-403 transfer policies / memo hooks, i.e. transfers can invoke callback code in the recipient. A malicious recipient can re-enter `withdraw` during the `safeTransfer`; on re-entry the balance has not yet been reduced, so the balance check passes again and another transfer fires.
- Impact: If the deposited token (or its transfer policy) yields control to the recipient during transfer, an attacker can recursively withdraw far more than their deposited balance, draining other users' funds. The fix is to update `balances`/`totalDeposits` before the external transfer (or add a reentrancy guard).

