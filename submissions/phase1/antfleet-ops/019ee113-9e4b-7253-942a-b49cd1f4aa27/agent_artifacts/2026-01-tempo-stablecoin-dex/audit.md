# Audit: 2026-01-tempo-stablecoin-dex

## Unauthorized Order Cancellation
- Location: `StablecoinDEX.sol` : `cancel()`
- Mechanism: The `cancel` function checks that the order exists (`order.maker != address(0)`) but performs no authorization check to verify that `msg.sender == order.maker`. Any external caller can invoke `_cancelOrder` on any active order in the book. Because cancellation refunds the remaining base tokens back to the original maker (not the caller), this is not directly a theft vector, but it completely breaks order integrity.
- Impact: A malicious actor can grief market makers and takers by arbitrarily removing orders from the book. An attacker can cancel orders just before a taker's transaction is mined (mempool front-running), or systematically cancel all orders to halt trading. This enables orderbook manipulation and denial-of-service against legitimate liquidity providers.

---

## Unchecked Arithmetic in Emergency Withdrawal (Token Theft)
- Location: `StablecoinDEX.sol` : `_processWithdrawal()` (called by `emergencyWithdraw()`)
- Mechanism: The `_processWithdrawal` function wraps the balance decrements in an `unchecked` block:
  ```solidity
  unchecked {
      balances[user][token] -= amount;
      totalDeposits[token] -= amount;
  }
  IERC20(token).safeTransfer(user, amount);
  ```
  Unlike the public `withdraw()` function—which requires `balances[msg.sender][token] >= amount`—`emergencyWithdraw` performs no balance validation before the unchecked subtraction. If `amount > balances[user][token]`, the uint128 subtraction silently wraps to a near-`type(uint128).max` value. The contract then transfers `amount` tokens to the caller. After the underflow, the attacker's recorded balance is enormous, allowing repeated withdrawals that drain the contract's actual token holdings (which belong to other depositors).
- Impact: An attacker can drain all tokens from the contract, stealing funds belonging to other users. For example, with the contract holding 100 tokens and an attacker having deposited 1 token, the attacker calls `emergencyWithdraw(token, 100)`, the internal balance underflows to `2^128 - 99`, and the attacker receives 100 tokens. They can repeat this in increments until the contract is emptied. If the token implements callbacks (ERC-777 / hookable tokens), this can be escalated into a single-transaction reentrancy drain, compounding the loss.

---

## Missing Maker Authorization on Cancel (Reinforces #1)
- Location: `StablecoinDEX.sol` : `_cancelOrder()` (called by `cancel()` and indirectly via `cancel`)
- Mechanism: The internal `_cancelOrder` function trusts that the caller has already validated authorization. Since the only caller (`cancel`) does not perform this check, the helper assumes trust it never receives. This is the root cause of the missing-access-control issue.
- Impact: Same as Finding #1 — enables arbitrary order removal by any participant, undermining the orderbook's integrity and enabling griefing/front-running attacks against both makers and takers.
