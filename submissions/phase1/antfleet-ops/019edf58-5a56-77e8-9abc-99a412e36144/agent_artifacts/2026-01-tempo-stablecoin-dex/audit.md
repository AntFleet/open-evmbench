# Audit: 2026-01-tempo-stablecoin-dex

# Security Audit Report

## Unchecked Underflow in emergencyWithdraw Drains All Contract Funds
- Location: StablecoinDEX.sol : `emergencyWithdraw` / `_processWithdrawal`
- Mechanism: `emergencyWithdraw` is public with no access control and calls `_processWithdrawal`, which performs `balances[user][token] -= amount` and `totalDeposits[token] -= amount` inside an `unchecked` block **without first verifying** that the user's balance is sufficient. When `amount` exceeds the caller's balance, the subtraction silently underflows (wrapping to a near-`type(uint128).max` value). The subsequent `safeTransfer(user, amount)` then transfers `amount` real tokens to the caller, draining the contract's token holdings up to its actual ERC-20 balance.
- Impact: Any attacker can call `emergencyWithdraw(token, contractTokenBalance)` with zero prior deposits and steal every token of every type held by the contract, stealing all user deposits and locked order funds.

## Missing Authorization in cancel — Anyone Can Cancel Any Order
- Location: StablecoinDEX.sol : `cancel`
- Mechanism: `cancel` checks only that the order exists (`order.maker != address(0)`) but never verifies that `msg.sender == order.maker`. It then calls `_cancelOrder`, which refunds the locked `remaining` tokens to the original maker and unlinks the order from the orderbook.
- Impact: Any attacker can grief all market makers by repeatedly cancelling their open orders the moment they are placed, permanently disrupting order flow and liquidity provision. While funds are returned to the maker (not stolen), the DOS makes the DEX unusable for makers.

## Checks-Effects-Interactions Violation in withdraw (Reentrancy)
- Location: StablecoinDEX.sol : `withdraw`
- Mechanism: `withdraw` calls `IERC20(token).safeTransfer(msg.sender, amount)` **before** decrementing `balances[msg.sender][token]`. Because the contract accepts arbitrary token addresses via `deposit`, a malicious or callback-capable token (e.g., ERC-777) can reenter `withdraw` during the external call. On reentry, the balance has not yet been reduced, so the guard `balances[msg.sender][token] < amount` passes again, allowing a second (and repeated) withdrawal of the same funds.
- Impact: An attacker who deposits a callback-capable or malicious token can withdraw their balance multiple times, stealing other users' tokens from the contract.

## MAX_PRICE_DEVIATION Constant Defined but Never Enforced
- Location: StablecoinDEX.sol : `placeOrder` / `fillOrder`
- Mechanism: The contract declares `MAX_PRICE_DEVIATION = 1e16` (1% from parity) and the documentation states the DEX is for stablecoin pairs near 1:1, but neither `placeOrder` nor `fillOrder` ever references this constant. Orders can be created at any arbitrary price, including extreme values far from parity.
- Impact: Makers can place orders at manipulative prices. Combined with the lack of price-sorted orderbook insertion, takers could unknowingly fill orders at severely off-market rates, or the contract could be used for non-stablecoin speculation contrary to its stated invariant, undermining any downstream system that trusts orders respect the parity bound.

## No baseToken != quoteToken Check — Self-Referential Orders
- Location: StablecoinDEX.sol : `placeOrder`
- Mechanism: `placeOrder` never verifies that `baseToken != quoteToken`. An order where both are the same token creates a circular swap: the maker locks `amount` of token X, and a taker pays `quoteAmount` of token X to receive `amount` of token X. With a price below 1e18, a taker profits by buying the maker's locked tokens at a discount.
- Impact: A user can create misleading or exploitative self-referential orders. While self-harm is possible for the maker, the primary risk is accounting confusion and potential integration issues for off-chain systems that assume distinct token pairs.
