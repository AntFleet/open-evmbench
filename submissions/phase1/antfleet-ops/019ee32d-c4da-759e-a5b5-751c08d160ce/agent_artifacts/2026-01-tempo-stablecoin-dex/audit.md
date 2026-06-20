# Audit: 2026-01-tempo-stablecoin-dex

## Unprotected Emergency Withdrawal Allows Arbitrary Fund Theft
- Location: `StablecoinDEX.sol` : `emergencyWithdraw` (incorporating `_processWithdrawal`)
- Mechanism: The function `emergencyWithdraw` is declared `external` but completely lacks access control policies and does not verify if the caller has any deposited balance. It directly executes `_processWithdrawal`, which subtracts the requested `amount` from the user's balance and `totalDeposits` inside an `unchecked` block. Since there is no validation to ensure the caller's balance is greater than or equal to `amount`, subtracting from an insufficient or zero balance results in an underflow, wrapping the user's recorded balance to a massive positive value. The function then proceeds to invoke transfer logic and sends the requested tokens to the caller as long as the contract holds enough token reserves.
- Impact: Any malicious actor can call `emergencyWithdraw` with an amount up to the contract's total holdings for any token and immediately drain all depositor funds from the DEX.

## Missing Access Control on Order Cancellation
- Location: `StablecoinDEX.sol` : `cancel`
- Mechanism: The `cancel` function allows anyone to pass an arbitrary `orderId` to cancel an open order. It retrieves the order target but fails to verify that the message sender (`msg.sender`) corresponds to the creator/maker of the order (`order.maker`). It proceeds to invoke `_cancelOrder`, which deletes the order metadata from storage and refunds the remaining locked base tokens back to the maker's balance.
- Impact: An attacker can cancel all open liquidity orders in the exchange's orderbook. While the funds are refunded to their original creators rather than stolen by the attacker, this allows anyone to execute a complete denial of service (DoS) and permanently disrupt the trading operations of market makers.

## Reentrancy and Checks-Effects-Interactions Violation in Standard Withdrawal
- Location: `StablecoinDEX.sol` : `withdraw`
- Mechanism: The `withdraw` function violates the Checks-Effects-Interactions (CEI) security pattern by transferring tokens to the caller via `IERC20(token).safeTransfer(msg.sender, amount)` before updating internal state variables (`balances[msg.sender][token]` and `totalDeposits[token]` are updated after the transfer). For stablecoins that employ transfer policies with hooks or callback receivers (such as custom compliance-aware stablecoins, ERC-777, or certain implementations of the TIP-20 standard), the receiver can hijack control flow during the transfer and recursively call `withdraw` before their state balance is decremented.
- Impact: An attacker can execute a reentrancy attack to recursively withdraw assets using the same initial balance, allowing them to rapidly drain all contract liquidity.
