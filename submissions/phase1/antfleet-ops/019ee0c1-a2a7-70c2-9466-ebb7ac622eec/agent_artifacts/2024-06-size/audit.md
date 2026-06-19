# Audit: 2024-06-size

## Borrow aToken cap bypass through multicall
- Location: `src/libraries/Multicall.sol` : `multicall`
- Mechanism: `Deposit.executeDeposit` skips `validateBorrowATokenCap()` whenever `state.data.isMulticall` is true, relying on the final multicall cap check. That final check records `state.data.borrowAToken.balanceOf(address(this))`, even though `CapsLibrary.validateBorrowATokenIncreaseLteDebtTokenDecrease` expects total borrow aToken supply. A borrow-token deposit minted to the user increases total supply but not the Size contract’s own balance, so `multicall([deposit(borrowToken, amount, attacker)])` bypasses the cap entirely.
- Impact: An attacker can mint borrow aTokens above `borrowATokenCap`, bypassing the protocol’s exposure/risk limit and potentially griefing the market by leaving the cap permanently exceeded.

## Non-18-decimal collateral is valued incorrectly
- Location: `src/libraries/RiskLibrary.sol` : `collateralRatio`; `src/libraries/AccountingLibrary.sol` : `debtTokenAmountToCollateralTokenAmount`
- Mechanism: Debt is normalized to wad, but collateral balances are used in raw token units. The code allows collateral tokens with decimals up to 18, but never scales `collateralToken.balanceOf(account)` to 18 decimals and never scales collateral amounts back down when converting debt to collateral. For collateral tokens with fewer than 18 decimals, users appear undercollateralized by `10 ** (18 - collateralDecimals)`, and liquidation math treats the collateral needed to cover debt as far larger than reality.
- Impact: In any market using non-18-decimal collateral, healthy borrowers can be falsely liquidated. Liquidators can pay the debt amount and receive the borrower’s entire pro-rata collateral, draining collateral at a large discount.

## Liquidation reward uses borrow-token units as collateral-token units
- Location: `src/libraries/actions/Liquidate.sol` : `executeLiquidate`
- Mechanism: The liquidation reward cap is computed as `debtPosition.futureValue * liquidationRewardPercent`, where `futureValue` is denominated in borrow-token units. It is compared directly against `assignedCollateral - debtInCollateralToken`, which is denominated in collateral-token units. The cap should be based on `debtInCollateralToken`, not raw borrow debt.
- Impact: For configurations such as 18-decimal borrow tokens against valuable 18-decimal collateral, liquidators can receive far more collateral than intended, potentially taking the entire surplus collateral of an overdue or underwater loan. Other decimal/price combinations can also make liquidations economically unviable.

## Exact-cash-out borrowing undercharges swap fees
- Location: `src/libraries/AccountingLibrary.sol` : `getCreditAmountIn`; `src/libraries/actions/SellCreditMarket.sol` : `executeSellCreditMarket`
- Mechanism: When `sellCreditMarket` is called with `exactAmountIn == false`, `creditAmountIn` is calculated by inverting through `PERCENT - swapFeePercent`, which implies the swap fee is charged on the gross pre-fee cash amount. But the returned `fees` are calculated as `cashAmountOut * swapFeePercent / PERCENT`, charging only on the net cash sent to the borrower. Execution transfers only `cashAmountOut + fees` from the lender while issuing credit as if the larger gross amount had been paid.
- Impact: Lenders receive more future credit than they actually paid for, capturing part of the intended protocol swap fee. Colluding users can systematically underpay protocol fees, and non-colluding borrowers can receive loans mispriced relative to the lender’s effective return.

