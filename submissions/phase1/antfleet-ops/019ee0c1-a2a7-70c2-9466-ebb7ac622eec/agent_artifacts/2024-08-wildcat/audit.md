# Audit: 2024-08-wildcat

## Pending withdrawal batch remains mutable after market close

- Location: `src/market/WildcatMarket.sol : closeMarket`; `src/market/WildcatMarketWithdrawals.sol : _executeWithdrawal` / `_queueWithdrawal`
- Mechanism: `closeMarket()` can pay the current pending withdrawal batch but leaves `state.pendingWithdrawalExpiry` pointing at that batch. Because `_executeWithdrawal()` skips the expiry check once `state.isClosed` is true, an account can execute a withdrawal from that still-pending batch before it is finalized. Later, `_queueWithdrawal()` sees the nonzero `pendingWithdrawalExpiry` and adds new closed-market withdrawal requests into the same already-executed batch, increasing `batch.scaledTotalAmount` after earlier users have claimed using the old denominator.
- Impact: A lender can manipulate a closed market’s pending batch so early claimants withdraw against one batch share calculation while later withdrawals are added under another. This lets some lenders drain the batch’s reserved assets and leaves later lenders unable to withdraw their funds.

