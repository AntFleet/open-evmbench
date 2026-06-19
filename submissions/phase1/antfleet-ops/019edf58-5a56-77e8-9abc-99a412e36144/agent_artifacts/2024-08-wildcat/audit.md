# Audit: 2024-08-wildcat

## FixedTermLoanHooks Prevents Sanctioned Account Blocking (nukeFromOrbit)
- Location: `src/access/FixedTermLoanHooks.sol` : `onQueueWithdrawal`
- Mechanism: `nukeFromOrbit` calls `_blockAccount`, which calls `_queueWithdrawal`, which invokes `hooks.onQueueWithdrawal`. In `FixedTermLoanHooks.onQueueWithdrawal`, the first check is `if (market.fixedTermEndTime > block.timestamp) revert WithdrawBeforeTermEnd()`. This reverts unconditionally before any other logic, preventing the forced withdrawal from being queued. Since the entire `nukeFromOrbit` transaction reverts, the sanctioned account's balance remains untouched and they retain full control of their position.
- Impact: A sanctioned account on a fixed-term market cannot be blocked or force-liquidated via `nukeFromOrbit` until the fixed term expires. This completely defeats the sanctions compliance mechanism for these markets, allowing sanctioned entities to maintain their positions indefinitely (up to the fixed term).

## `grantRole` Accepts Future Timestamps, Extending Credential Validity Beyond TTL
- Location: `src/access/AccessControlHooks.sol` : `_grantRole` (also in `src/access/FixedTermLoanHooks.sol` : `_grantRole`)
- Mechanism: `_grantRole` only checks `if (newExpiry < block.timestamp) revert GrantedCredentialExpired()` but never validates that `roleGrantedTimestamp <= block.timestamp`. Since `newExpiry = roleGrantedTimestamp + timeToLive`, a provider can pass a `roleGrantedTimestamp` far in the future, making `newExpiry` well beyond what the TTL should allow. The credential is then stored via `setCredential`. Later, `credentialNotExpired` only checks `calculateExpiry(lastApprovalTimestamp) >= block.timestamp`, so the credential is treated as valid. This is inconsistent with the pull-based paths (`_tryGetCredential` and `_tryValidateCredential`), which both reject timestamps `> block.timestamp`.
- Impact: An approved role provider can grant credentials with effectively unbounded validity periods, bypassing the TTL limit set by the borrower. For example, with a TTL of 1 day, a provider could set `roleGrantedTimestamp = block.timestamp + 364 days`, yielding a credential valid for 365 days instead of 1.

## `closeMarket` Loop Does Not Check Available Liquidity, Wastes Gas on Unpaid Batches
- Location: `src/market/WildcatMarket.sol` : `closeMarket`
- Mechanism: The loop `for (uint256 i; i < numBatches; i++)` processes unpaid batches but does not break when `availableLiquidity` reaches 0. Each subsequent iteration calls `_processUnpaidWithdrawalBatch` with zero liquidity, which performs storage reads and a no-op `_applyWithdrawalBatchPayment` before continuing. Compare with `repayAndProcessUnpaidWithdrawalBatches` which correctly uses `while (i++ < numBatches && availableLiquidity > 0)`.
- Impact: If there are many unpaid batches and insufficient liquidity to pay them all, the `closeMarket` call will waste gas iterating through all remaining batches with zero liquidity before ultimately reverting at `revert_CloseMarketWithUnpaidWithdrawals()`. This could make closing a market with many unpaid batches prohibitively expensive, potentially locking the market open.
