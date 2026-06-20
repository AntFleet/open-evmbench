# Audit: 2024-06-size

## Exact-cash-out sales undercharge swap fees
- Location: `src/libraries/AccountingLibrary.sol` : `getCreditAmountIn`; `src/libraries/actions/SellCreditMarket.sol` : `executeSellCreditMarket`
- Mechanism: For `sellCreditMarket(..., exactAmountIn == false)`, `creditAmountIn` is grossed up using `PERCENT - swapFeePercent`, which implies the swap fee is charged on the pre-fee gross cash amount. But `fees` is computed as `cashAmountOut * swapFeePercent / PERCENT`, i.e. on the net amount sent to the borrower.
- Impact: Borrowers/lenders can route through exact-cash-out trades to pay less protocol fee than intended. The lender receives credit as if the full gross fee was paid, while the fee recipient is underpaid.

## Repay can pay a replacement borrower’s debt
- Location: `src/libraries/actions/Repay.sol` : `validateRepay` / `executeRepay`; `src/libraries/actions/LiquidateWithReplacement.sol` : `executeLiquidateWithReplacement`
- Mechanism: `RepayParams` only identifies a `debtPositionId`; it does not bind repayment to the expected borrower. `liquidateWithReplacement` liquidates the original borrower, then reuses the same debt position ID by changing `debtPosition.borrower` and restoring `futureValue`. A borrower’s pending `repay` transaction can therefore execute after replacement and repay the new borrower’s debt.
- Impact: A borrower trying to repay to avoid liquidation can be liquidated first, lose collateral, then also transfer borrow tokens to repay the replacement borrower’s debt.

## Liquidation remainder cap is too large
- Location: `src/libraries/actions/Liquidate.sol` : `executeLiquidate`
- Mechanism: After paying the liquidator, the protocol caps the collateral remainder with `debtInCollateralToken * crLiquidation / PERCENT`. Since the debt principal is already accounted for in `debtInCollateralToken`, the cap should apply only to excess collateral, i.e. `crLiquidation - PERCENT`. Using the full liquidation CR lets the protocol-fee split apply to too much borrower surplus.
- Impact: Overdue profitable liquidations can take excessive collateral from borrowers, especially borrowers with higher collateral ratios, causing larger-than-intended losses.

## Liquidation reward uses borrow-token units as collateral-token units
- Location: `src/libraries/actions/Liquidate.sol` : `executeLiquidate`
- Mechanism: `liquidatorReward` is computed from `debtPosition.futureValue * liquidationRewardPercent`, where `futureValue` is denominated in borrow-token units, then added to `debtInCollateralToken`, which is denominated in collateral-token units. The reward should be based on the converted collateral value.
- Impact: For common pairs like USDC debt against WETH collateral, liquidator rewards become near-zero, making liquidations uneconomic and allowing bad debt to persist. Other token/decimal combinations can overpay liquidators from borrower collateral.

