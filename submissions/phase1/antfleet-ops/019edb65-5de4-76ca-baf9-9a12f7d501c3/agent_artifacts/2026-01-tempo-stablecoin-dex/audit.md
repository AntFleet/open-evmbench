# Audit: 2026-01-tempo-stablecoin-dex

## 1. Reentrancy in `withdraw` allows draining of deposited tokens
- **Location:** `contracts/StablecoinDEX.sol` : `withdraw()`
- **Mechanism:** The `withdraw` function performs an external `safeTransfer` call **before** updating the user’s balance. If the token contract is malicious (or an ERC-777-like token with hooks), the recipient can reenter `withdraw` during the transfer. Because the balance has not yet been decremented, the `require` check passes again, allowing the attacker to withdraw the same tokens multiple times, effectively draining the entire balance of that token held by the contract.
- **Impact:** An attacker can steal all tokens of a given type from the DEX, including funds deposited by other users.

## 2. Anyone can cancel any order (missing access control)
- **Location:** `contracts/StablecoinDEX.sol` : `cancel()`
- **Mechanism:** The `cancel` function only checks that the order exists (`order.maker != address(0)`), but does **not** verify that `msg.sender` is the order’s maker (`order.maker`). As a result, any address can call `cancel` on any open order, forcibly removing it from the order book and refunding the locked base tokens to the original maker. This completely bypasses the intended maker-only cancellation.
- **Impact:** An attacker can grief market makers by cancelling their orders, disrupting the order book and preventing normal trading. The maker loses their position and may suffer financial loss due to missed trading opportunities.

## 3. Unprotected `emergencyWithdraw` allows unconditional draining of all tokens
- **Location:** `contracts/StablecoinDEX.sol` : `emergencyWithdraw()`
- **Mechanism:** The `emergencyWithdraw` function is `external` and has **no access control** (no owner/admin modifier, no balance check). It calls `_processWithdrawal`, which uses an `unchecked` block to subtract `amount` from `balances[user][token]` and `totalDeposits[token]` **before** transferring the tokens. An attacker can call `emergencyWithdraw` with an amount greater than their actual balance; the unchecked subtraction will silently underflow, giving them a huge (undercounted) balance, and the contract will transfer real tokens to the attacker. The attacker can repeat this to drain the entire token balance of the contract.
- **Impact:** Any user can steal all tokens of any type held by the DEX, completely draining the liquidity pool. This is a critical, direct loss-of-funds vulnerability.
