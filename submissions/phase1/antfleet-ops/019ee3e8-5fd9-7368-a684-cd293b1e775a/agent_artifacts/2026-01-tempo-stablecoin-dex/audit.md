# Audit: 2026-01-tempo-stablecoin-dex

## Unprotected Function
- Location: contracts/StablecoinDEX.sol : function emergencyWithdraw
- Mechanism: The `emergencyWithdraw` function does not check if the caller has enough balance, allowing an attacker to drain the contract's funds. Additionally, it does not verify if the token is one of the allowed tokens for withdrawal, potentially enabling the draining of arbitrary tokens.
- Impact: An attacker can use this function to steal all tokens from the contract, causing users to lose their funds.

## Unchecked Arithmetic
- Location: contracts/StablecoinDEX.sol : function _processWithdrawal
- Mechanism: Although the use of `unchecked` arithmetic in `_processWithdrawal` is intended for gas optimization, it could lead to underflow/overflow issues if the subtraction operation attempts to reduce the balance below zero or exceeds the maximum value that can be represented.
- Impact: If an attacker finds a scenario where an underflow/overflow occurs, they could potentially manipulate the balance of users, enabling them to withdraw more tokens than they are supposed to.

## Unsecured Order Head Update
- Location: contracts/StablecoinDEX.sol : function placeOrder
- Mechanism: When a new order is placed, the `orderHeads` mapping is updated directly with the new order ID. However, this update does not consider the possibility of an order with a price that is significantly different from the current market price, potentially disrupting the order book.
- Impact: An attacker could exploit this by placing orders with very low or very high prices, affecting the market dynamics and potentially profiting from manipulation.

## Reentrancy Vulnerability
- Location: contracts/StablecoinDEX.sol : function fillOrder
- Mechanism: The `fillOrder` function first updates the order's remaining amount and then executes the swap. However, it does not check for potential reentrancy attacks, where an attacker could reenter the function before the swap is completed, potentially draining the contract.
- Impact: An attacker could exploit this vulnerability by reentering the `fillOrder` function multiple times, draining the contract of its funds or causing unintended behavior.

## No Rate Limiting
- Location: contracts/StablecoinDEX.sol : function fillOrder, function placeOrder
- Mechanism: The contract does not implement rate limiting on functions like `fillOrder` and `placeOrder`, allowing an attacker to potentially spam these functions and cause a Denial of Service (DoS) or manipulate market prices.
- Impact: An attacker could exploit this by placing a large number of orders or filling orders rapidly, disrupting the normal operation of the contract and potentially profiting from the chaos.

## Lack of Access Control
- Location: contracts/StablecoinDEX.sol : function emergencyWithdraw
- Mechanism: The `emergencyWithdraw` function does not have proper access control, allowing anyone to call it and potentially drain the contract's funds.
- Impact: An attacker could use this function to steal all tokens from the contract, causing users to lose their funds.
