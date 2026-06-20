# Audit: 2024-04-noya

## Access Control Logic Error in Maintainer Modifier
- Location: contracts/accountingManager/Registry.sol : onlyVaultMaintainer
- Mechanism: The modifier evaluates `if (msg.sender != vaults[_vaultId].maintainer || hasRole(EMERGENCY_ROLE, msg.sender) == false)` before allowing execution. This is logically equivalent to requiring *both* `msg.sender == maintainer` *and* `hasRole(EMERGENCY_ROLE)` to be true (i.e. the negation of an OR condition was written with an inverted `||` + `== false`).
- Impact: Legitimate maintainers without the emergency role are permanently denied access to all maintainer-only functions (add/remove connectors, update trusted tokens/positions, etc.), while only the intersection of the two roles can act. An attacker with the emergency role but not maintainer is also blocked.

## Incorrect Debt Accounting in Fulfill/Execute Withdraw Path
- Location: contracts/accountingManager/AccountingManager.sol : fulfillCurrentWithdrawGroup + executeWithdraw
- Mechanism: `fulfillCurrentWithdrawGroup` sets `totalABAmount` to `min(availableAssets, totalCBAmount)` and `totalCBAmountFullfilled = totalCBAmount`. `executeWithdraw` then scales every user's `baseTokenAmount = data.amount * totalABAmount / totalCBAmountFullfilled`. When `availableAssets < totalCBAmount`, users receive a pro-rata haircut, but `totalWithdrawnAmount` is still incremented by the *full* `processedBaseTokenAmount` (the pre-haircut `data.amount` values).
- Impact: `getProfit()` (and therefore performance fees, `totalProfitCalculated`, and all accounting invariants) becomes permanently inflated by the haircut amount. An attacker (or the manager) can repeatedly trigger partial fulfillment cycles to siphon extra profit-based fees.

## Missing Reentrancy Protection on External Connector Calls
- Location: contracts/accountingManager/AccountingManager.sol : executeDeposit (the `IConnector(connector).addLiquidity` call) and retrieveTokensForWithdraw
- Mechanism: Both functions are marked `nonReentrant`, but the external call to an arbitrary connector occurs *after* state updates that affect accounting (`_mint`, `totalDepositedAmount`, `amountAskedForWithdraw`). The connector's `addLiquidity` / `sendTokensToTrustedAddress` can re-enter the AccountingManager via `sendTokensToTrustedAddress` (which only checks `isAnActiveConnector`).
- Impact: Re-entrancy can be used to mint shares or drain base tokens before the original call finishes, bypassing the deposit/withdraw queue invariants and the `withdrawRequestsByAddress` balance check.

## Unsafe Token Transfer in sendTokensToTrustedAddress
- Location: contracts/accountingManager/AccountingManager.sol : sendTokensToTrustedAddress
- Mechanism: When `registry.isAnActiveConnector(vaultId, msg.sender)` is true, the function performs `safeTransfer(address(msg.sender), amount)` using the *caller's* `msg.sender` rather than the `_caller` parameter. The function is also callable by anyone; the registry check only gates the transfer.
- Impact: Any active connector can be tricked (via a malicious `_data` payload or re-entrancy) into transferring tokens to an arbitrary address chosen by the connector itself, bypassing the intended recipient.

## Oracle / TVL Manipulation via resetMiddle
- Location: contracts/accountingManager/AccountingManager.sol : resetMiddle + calculateDepositShares / calculateWithdrawShares
- Mechanism: `resetMiddle` (callable by `onlyManager`) can arbitrarily move the `middle` pointer of either queue to any value between `first` and the current `middle`. The calculation functions only process requests whose `recordTime <= oldestUpdateTime`. A manager can therefore selectively re-process (or skip) deposits/withdrawals after a price movement.
- Impact: The manager can force users into a later (more favorable or less favorable) share-price calculation window, enabling direct theft of value from queued users or extraction of extra performance fees.

## Unchecked Return Value from Connector sendTokensToTrustedAddress
- Location: contracts/accountingManager/AccountingManager.sol : retrieveTokensForWithdraw
- Mechanism: The loop blindly does `amountAskedForWithdraw_temp += retrieveData[i].withdrawAmount` regardless of the value returned by `IConnector(...).sendTokensToTrustedAddress`. The subsequent balance check only verifies `balanceBefore + amount > balanceAfter` using the returned `amount`, not the requested amount.
- Impact: A malicious or buggy connector can return 0 (or a smaller amount) while the accounting still records the full requested withdrawal, allowing the manager to overstate `amountAskedForWithdraw` and incorrectly fulfill withdrawal groups.
