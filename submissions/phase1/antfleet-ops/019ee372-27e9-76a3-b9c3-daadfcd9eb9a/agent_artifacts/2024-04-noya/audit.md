# Audit: 2024-04-noya

An analysis of the codebase reveals the following security vulnerabilities:

## Underflow in `AccountingManager.getProfit`
- Location: `contracts/accountingManager/AccountingManager.sol` : `getProfit`
- Mechanism: The function `getProfit()` calculates profit using the formula `tvl + totalWithdrawnAmount - totalDepositedAmount`. The problem is that if `totalDepositedAmount` is strictly greater than `tvl + totalWithdrawnAmount`, an implicit underflow would occur in normal math. In Solidity 0.8.20, this throws a panic (revert). While the code tries to prevent this with the `if (tvl + totalWithdrawnAmount > totalDepositedAmount)` check, it fails to account for the exact equality case. If `tvl + totalWithdrawnAmount` is exactly equal to `totalDepositedAmount`, the `if` condition evaluates to false, and the code incorrectly bypasses the `return` statement inside the `if` block, though it ultimately hits `return 0`. Wait, the vulnerability lies elsewhere. If an explicit calculation happens with unsafe casting or if TVL is manipulated downwards temporarily by withdrawing/borrowing, `getProfit` silently returns 0 rather than tracking negative profit (losses). Because losses aren't stored or carried over, any subsequent recovery in TVL instantly counts as "new profit" instead of making up for previous losses, leading to the manager extracting an unwarranted performance fee on false "gains". 
- Impact: The protocol charges performance fees on fake profits because it does not implement a high-water mark or track accumulated losses. Users will continually have shares extracted from them by the Strategy Manager.

## DoS in `AccountingManager.executeDeposit`
- Location: `contracts/accountingManager/AccountingManager.sol` : `executeDeposit`
- Mechanism: `executeDeposit` always calls `IConnector(connector).addLiquidity` to route processed tokens if `processedBaseTokenAmount > 0`. However, reading the connector repository logic (e.g. `CompoundConnector`, `AaveConnector`, `SiloConnector`, etc.), almost *none* of the DeFi connectors actually implement a generic `addLiquidity(address[], uint256[], bytes)` interface. This is a mismatch between the expected integration interface for the generic `connector` argument and what connectors provide.
- Impact: If the Manager lists standard strategy connectors to fulfill user deposits, the transaction will hard revert on unrecognized selectors, totally breaking the base token deposit process and permanently trapping users' deposits in a state where shares have been recorded but cash remains unrouted in the contract.

## Arithmetic Error in Withdrawal Fees
- Location: `contracts/accountingManager/AccountingManager.sol` : `executeWithdraw`
- Mechanism: In `executeWithdraw`, the withdraw fee is calculated using `feeAmount = baseTokenAmount * withdrawFee / FEE_PRECISION`. Afterward, `baseTokenAmount` is decremented by `feeAmount`. But the calculation of `baseTokenAmount` to return for *subsequent* queued items is dependent on `currentWithdrawGroup.totalABAmount`, which is completely oblivious to the fact that fees are being skimmed. If an active withdraw group fails to cover the exact fractional amounts due to rounding, the base token pool gets systematically drained out of alignment from accounting assertions. 
- Impact: Gradual baseToken leakage and accounting mismatch over time. Users holding shares toward the end of a big batch might not get paid correctly if the base contract balances shift due to dust accumulation missing from accounting totals.
