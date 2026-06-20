# Audit: 2024-06-size

An issue with the protocol's fee calculation exists in `AccountingLibrary` specifically regarding how `exactAmountIn = false` orders are handled during market borrowing, which leads to inconsistent swap fee charges.

## Incorrect Swap Fee Calculation for `exactAmountIn = false` in `getCreditAmountIn`
- Location: `src/libraries/AccountingLibrary.sol`  :  `getCreditAmountIn`
- Mechanism: The protocol charges a swap fee to order takers based on the total cash exchanged (`cashAmountIn`). When calculating fees from `cashAmountIn` (such as in `getCashAmountIn`), it accurately applies the fee percentage (`fees = cashAmountIn * swapPercent`). However, when calculating from `cashAmountOut` using `getCreditAmountIn`, the fee is incorrectly calculated against the net payout (`cashAmountOut`):
```solidity
 fees = Math.mulDivUp(cashAmountOut, swapFeePercent, PERCENT);
```
Since `cashAmountIn = cashAmountOut + fees`, the fee should be sized against `cashAmountIn` (i.e. `fees = cashAmountOut * swap / (PERCENT - swap)`). By sizing it against the lower `cashAmountOut`, the protocol undervalues the swap fee relative to the same size order matching with reverse inputs.
Furthermore, the `maxCredit` formula passed from `SellCreditMarket` multiplies by `(PERCENT + ratePerTenor)` and divides by `(PERCENT - swapFeePercent)`. 
- Impact: A borrower who specifies exactly how much cash to receive via market sell orders will unfairly bypass a portion of the protocol's intended swap fees. Attackers can exploit this accounting discrepancy to systemically underpay fees on precise borrowing matching, causing revenue loss compared to standard exact amount-in operations.
