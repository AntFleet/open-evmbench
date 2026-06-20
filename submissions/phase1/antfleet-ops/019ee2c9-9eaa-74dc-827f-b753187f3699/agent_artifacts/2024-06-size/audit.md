# Audit: 2024-06-size

## `borrowATokenCap` can be bypassed through `multicall`
- Location: `src/libraries/Multicall.sol` : `multicall`; `src/libraries/actions/Deposit.sol` : `executeDeposit`
- Mechanism: Borrow-token deposits normally enforce the cap in `executeDeposit` via `validateBorrowATokenCap()`, but that check is skipped whenever `state.data.isMulticall` is true. The fallback check in `multicall` is meant to compare pre/post borrow-aToken supply, but it snapshots `state.data.borrowAToken.balanceOf(address(this))` instead of `totalSupply()`. A user deposit mints `borrowAToken` to `params.to`, so total supply increases while the protocol contract’s own balance stays unchanged. As a result, a borrow-token deposit wrapped in `multicall` bypasses both the per-call cap check and the post-batch cap check.
- Impact: Any user can exceed the configured `borrowATokenCap` arbitrarily by depositing through `multicall`, defeating the protocol’s supply/risk limit on exposure to the variable pool.

## Native ETH already held by the contract can be stolen by the next ETH depositor
- Location: `src/libraries/actions/Deposit.sol` : `executeDeposit`
- Mechanism: In the ETH/WETH path, once `msg.value > 0`, the function ignores `params.amount` and sets `amount = address(this).balance`, then wraps and credits that entire balance to the current depositor. Because most external entrypoints are `payable` and do not enforce `msg.value == 0`, and because ETH can also be forcibly sent to the contract, the contract can accumulate stray native ETH. The next valid ETH deposit then converts all of that ETH into WETH and mints protocol balance to the attacker.
- Impact: An attacker can steal any residual ETH sitting in the contract by making a minimal valid ETH deposit, capturing funds left behind by accidental transfers, overpayments, or forced ETH sends.

## Liquidation reward is computed in borrow-token units but paid in collateral-token units
- Location: `src/libraries/actions/Liquidate.sol` : `executeLiquidate`
- Mechanism: `debtInCollateralToken` is correctly converted into collateral-token units, but `liquidatorReward` is computed directly from `debtPosition.futureValue * liquidationRewardPercent / PERCENT`. `futureValue` is denominated in borrow-token units, and that raw number is then added to a collateral-token amount without conversion. In a typical setup like USDC debt against WETH collateral, this makes the reward off by token-decimal and price-scale differences.
- Impact: Liquidators can be paid far less than intended, making underwater positions economically unattractive to liquidate and allowing bad debt to persist; in other token/decimal configurations, the same bug can also overpay liquidators from borrower collateral.

## Exact-cash `sellCreditMarket` trades undercharge protocol swap fees
- Location: `src/libraries/AccountingLibrary.sol` : `getCreditAmountIn`; `src/libraries/actions/SellCreditMarket.sol` : `executeSellCreditMarket`
- Mechanism: For `sellCreditMarket(..., exactAmountIn = false)`, `getCreditAmountIn` solves `creditAmountIn` using `PERCENT - swapFeePercent`, which implies the requested `cashAmountOut` is net-of-fee. But it then returns `fees = cashAmountOut * swapFeePercent / PERCENT`, i.e. charging the fee on the net cash instead of on the gross pre-fee cash. The lender therefore transfers too little to `feeRecipient` while the debt/credit minted reflects the larger gross amount.
- Impact: Traders can systematically route through exact-cash-out sales to pay less than the configured protocol fee, siphoning value from protocol revenue on every such trade.

No additional high-confidence vulnerabilities stood out in the provided excerpt.

