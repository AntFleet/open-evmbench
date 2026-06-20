# Audit: 2024-06-size

## Borrow aToken cap bypass through multicall
- Location: `src/libraries/actions/Deposit.sol` : `executeDeposit`; `src/libraries/Multicall.sol` : `multicall`
- Mechanism: `executeDeposit` skips `validateBorrowATokenCap()` whenever `state.data.isMulticall` is true. The multicall end check is intended to allow deposits only when matched by debt reduction, but it snapshots `state.data.borrowAToken.balanceOf(address(this))`, not `borrowAToken.totalSupply()`. A user can call `multicall([deposit(underlyingBorrowToken, amount, attacker)])`; the user’s borrow aToken balance and total supply increase, while the protocol contract’s own balance does not, so the post-check passes.
- Impact: Anyone can deposit arbitrary borrow tokens above `borrowATokenCap`, bypassing the protocol’s configured exposure/risk limit.

## Liquidation reward uses borrow-token units as collateral-token units
- Location: `src/libraries/actions/Liquidate.sol` : `executeLiquidate`
- Mechanism: In profitable liquidations, `liquidatorReward` is capped with `debtPosition.futureValue * liquidationRewardPercent / PERCENT`. `futureValue` is denominated in borrow-token debt units, but the result is added to `debtInCollateralToken` and transferred as collateral tokens. The cap is not converted through `debtTokenAmountToCollateralTokenAmount`, so for common pairs like USDC debt and WETH collateral, the reward cap is USDC base units interpreted as wei.
- Impact: Liquidators receive a near-zero intended bonus for WETH/USDC-style deployments, making liquidations economically unattractive and allowing unsafe or overdue loans to remain unliquidated. With other decimal/price combinations, the cap can also be materially mis-sized.

## Non-18-decimal collateral breaks solvency and liquidation accounting
- Location: `src/libraries/RiskLibrary.sol` : `collateralRatio`; `src/libraries/AccountingLibrary.sol` : `debtTokenAmountToCollateralTokenAmount`
- Mechanism: Borrow-token amounts are normalized to wad via `amountToWad`, but collateral-token balances are used directly without normalizing by `underlyingCollateralToken.decimals()`. The initializer accepts any collateral token with `decimals() <= 18`, so non-18-decimal collateral is supported by validation but mis-accounted in CR and debt-to-collateral conversions.
- Impact: For collateral tokens with fewer than 18 decimals, users’ collateral ratios are massively understated and debt-to-collateral liquidation amounts are massively overstated. This can prevent valid borrowing and make liquidations/solvency checks incorrect, effectively breaking the market for such collateral assets.

