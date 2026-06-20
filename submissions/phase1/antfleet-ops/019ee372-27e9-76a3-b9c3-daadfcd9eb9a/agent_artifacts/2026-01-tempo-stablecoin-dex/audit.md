# Audit: 2026-01-tempo-stablecoin-dex

Here are the security vulnerabilities found in the provided codebase.

## 1. Unchecked Underflow Allows Complete Drain of Contract Funds
- **Location:** `StablecoinDEX.sol` : `emergencyWithdraw` and `_processWithdrawal`
- **Mechanism:** The `emergencyWithdraw` function calls the internal `_processWithdrawal` function, bypassing the balance checks that are normally enforced in the regular `withdraw` function. `_processWithdrawal` subtracts the requested `amount` from the user's balance inside an `unchecked` block. If the user's balance is less than `amount` (e.g., 0), the balance silently underflows to a massive number (`2^128 - amount`). 
- **Impact:** An attacker with zero balance can request an `emergencyWithdraw` up to the contract's actual token balance. The contract will send the attacker the tokens and simultaneously grant them an artificially massive balance, allowing them to repeatedly withdraw and drain all liquidity of any supported token from the DEX.

## 2. Unauthorized Order Cancellation
- **Location:** `StablecoinDEX.sol` : `cancel`
- **Mechanism:** The `cancel` function verifies that the order exists (`order.maker != address(0)`) but fails to verify that the caller is the owner of the order (`msg.sender == order.maker`).
- **Impact:** Any user or attacker can maliciously cancel any open limit order placed by any other user or market maker. This allows for a complete denial-of-service (DoS) on order placement and matching, severely disrupting the DEX orderbook and market maker operations.
