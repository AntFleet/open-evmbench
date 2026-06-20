# Audit: 2026-01-tempo-stablecoin-dex

**Emergency Withdraw Without Authorization or Balance Check**

- Location: `StablecoinDEX.sol` : `emergencyWithdraw`, `_processWithdrawal`
- Mechanism: `emergencyWithdraw` is callable by any address and directly invokes `_processWithdrawal`, which performs an unchecked subtraction on `balances[user][token]` and `totalDeposits[token]` followed by an unconditional `safeTransfer`. There is no `require(balances[msg.sender][token] >= amount)` (unlike the normal `withdraw` path) and no access control.
- Impact: Any attacker can withdraw arbitrary amounts of any token held by the contract, draining user deposits and breaking all accounting invariants.

**Unchecked Arithmetic Allows Underflow and State Corruption**

- Location: `StablecoinDEX.sol` : `_processWithdrawal`
- Mechanism: The function uses `unchecked { balances[user][token] -= amount; totalDeposits[token] -= amount; }` with no prior balance validation. When `amount > balances[user][token]`, the subtraction wraps around to a very large value.
- Impact: Attacker can set user balances to near-max values or cause `totalDeposits` to underflow, enabling further unauthorized withdrawals or denial-of-service via inconsistent accounting.

**Missing Quote Amount Validation Allows Overflow on Cast**

- Location: `StablecoinDEX.sol` : `fillOrder`
- Mechanism: `quoteAmount = (uint256(amount) * uint256(order.price)) / 1e18` is computed as `uint256` then cast to `uint128` without checking `quoteAmount <= type(uint128).max`. A maliciously high `price` or `amount` can cause the cast to revert or produce incorrect values before the balance check.
- Impact: Takers can cause transaction reverts on large/precise orders or, in edge cases, incorrect token transfers due to truncation.

**Order Linked-List Removal Leaves Stale Data**

- Location: `StablecoinDEX.sol` : `_cancelOrder`, `_removeFilledOrder`
- Mechanism: Both functions manually patch `prev`/`next` pointers and then zero only selected fields (`maker`, `baseToken`, etc.) or set `prev`/`next` to zero. The remaining fields (`price`, `amount`, `remaining`, `quoteToken`) are left with old values in storage.
- Impact: Subsequent calls to `getOrder` or iteration via `getOrders` can return partially valid stale order data, enabling incorrect routing decisions or false order existence checks.
