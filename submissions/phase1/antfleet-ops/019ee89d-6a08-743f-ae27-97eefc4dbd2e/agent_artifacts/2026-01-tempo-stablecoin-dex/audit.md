# Audit: 2026-01-tempo-stablecoin-dex

## Unauthenticated `emergencyWithdraw` drains the entire pool via unchecked underflow
- Location: contracts/StablecoinDEX.sol : `emergencyWithdraw` / `_processWithdrawal`
- Mechanism: `emergencyWithdraw` has no access control and performs no balance check; it forwards directly to `_processWithdrawal`, which subtracts inside an `unchecked` block (`balances[user][token] -= amount; totalDeposits[token] -= amount;`) and then calls `IERC20(token).safeTransfer(user, amount)`. Because the subtraction is unchecked and unguarded, a caller holding zero (or any insufficient) balance passes no validation — their stored balance silently underflows to ~2¹²⁸ while the contract transfers `amount` real tokens out. The attacker simply sets `amount` to the contract's full holding of the target token.
- Impact: Any account can call `emergencyWithdraw(token, contractBalance)` to sweep the entire pooled balance of any token out of the DEX, stealing all liquidity providers' deposits.

## Reentrancy in `withdraw` (transfer before balance update)
- Location: contracts/StablecoinDEX.sol : `withdraw`
- Mechanism: `withdraw` checks `balances[msg.sender][token] >= amount`, then performs the external `IERC20(token).safeTransfer(msg.sender, amount)` BEFORE decrementing `balances`/`totalDeposits` — a check-effects-interactions violation with no reentrancy guard anywhere in the contract. TIP-20 tokens integrate TIP-403 transfer policies / memo hooks that can hand control to attacker code during the transfer; the malicious recipient re-enters `withdraw` while `balances` still holds its pre-decrement value, repeatedly clearing the balance check and pulling tokens before any state is written.
- Impact: An attacker depositing a hook-bearing TIP-20 token can recursively withdraw and drain other depositors' holdings of that token far beyond their own credited balance.

## Missing maker authorization in `cancel`
- Location: contracts/StablecoinDEX.sol : `cancel`
- Mechanism: `cancel(orderId)` only verifies `order.maker != address(0)` and never checks `msg.sender == order.maker` before calling `_cancelOrder`, which unlinks the order and refunds `order.remaining` to the maker. The authorization check is entirely absent, so any address can cancel any open order belonging to anyone.
- Impact: An attacker can permissionlessly cancel every resting order in the book (or selectively cancel a counterparty's/competitor's order right before trading), destroying liquidity and disrupting MPP settlements — an orderbook-wide griefing/denial-of-service.

