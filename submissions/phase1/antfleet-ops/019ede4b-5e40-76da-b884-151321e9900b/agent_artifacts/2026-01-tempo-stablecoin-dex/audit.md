# Audit: 2026-01-tempo-stablecoin-dex

## Arbitrary Fund Drain via Unchecked Underflow in Emergency Withdrawal
- Location: `contracts/StablecoinDEX.sol` : `_processWithdrawal` (called by `emergencyWithdraw`)
- Mechanism: The `_processWithdrawal` function uses an `unchecked` block to subtract the withdrawal `amount` from `balances[user][token]` and `totalDeposits[token]` without first verifying that the user's balance is greater than or equal to the `amount`. In Solidity 0.8+, the `unchecked` keyword disables underflow protection. If a user calls `emergencyWithdraw` with an `amount` exceeding their actual balance, the balance subtraction will underflow and wrap around to a massive value near `2^128 - 1`. The contract then proceeds to execute the `safeTransfer` for the requested amount.
- Impact: An attacker can withdraw significantly more tokens than they deposited. By requesting an amount equal to the contract's total held balance, the attacker can completely drain the DEX of all funds deposited by other users.

## Missing Authorization in Order Cancellation
- Location: `contracts/StablecoinDEX.sol` : `cancel`
- Mechanism: The `cancel` function allows any external caller to cancel any open order by providing its `orderId`. The function only checks if the order exists (`order.maker == address(0)`) but entirely fails to verify that `msg.sender == order.maker`. While the `_cancelOrder` internal function correctly refunds the locked tokens to the original maker's balance, the lack of access control on the external entry point means any address can trigger the cancellation.
- Impact: An attacker can continuously monitor the mempool or iterate through order IDs to cancel all open orders on the DEX. This creates a severe Denial of Service (DoS) and griefing vector, completely halting the exchange's ability to match trades and forcing market makers to constantly waste gas re-placing their orders.

## Silent Truncation on Quote Amount Cast Leads to Accounting Error
- Location: `contracts/StablecoinDEX.sol` : `fillOrder`
- Mechanism: The `quoteAmount` is calculated as a `uint256` but is explicitly cast to `uint128` when updating user balances (`uint128(quoteAmount)`). In Solidity 0.8+, explicit narrowing casts do not revert on overflow; they silently truncate the higher bits. If a maker sets a sufficiently large `price` and a taker fills a large `amount`, the resulting `quoteAmount` can exceed the maximum value of `uint128` (~3.4e38). The truncated value will be significantly smaller than the actual calculated quote amount.
- Impact: A malicious taker can exploit this by filling orders with extremely large prices and amounts, causing the `quoteAmount` to overflow the `uint128` cast. The taker will pay only the truncated (much smaller) quote amount while receiving the full base token amount, effectively stealing funds from the maker.
