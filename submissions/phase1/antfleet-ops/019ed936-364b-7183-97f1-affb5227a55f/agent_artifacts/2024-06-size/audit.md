# Audit: 2024-06-size

## Consensus findings

## borrowATokenCap is bypassable via `multicall` due to a supply-metric mismatch
*(consensus — Reviewer A and Reviewer B)*
- Location: `src/libraries/Multicall.sol` : `multicall` (the `borrowATokenSupplyBefore` / `borrowATokenSupplyAfter` reads); `src/libraries/actions/Deposit.sol` : `executeDeposit`; `src/libraries/CapsLibrary.sol` : `validateBorrowATokenCap` and `validateBorrowATokenIncreaseLteDebtTokenDecrease`.
- Mechanism: The cap on deposited borrow tokens is normally enforced against the token's *total supply*: in a single-tx deposit `executeDeposit` calls `validateBorrowATokenCap()`, which reverts when `state.data.borrowAToken.totalSupply() > state.riskConfig.borrowATokenCap`. Inside a `multicall`, `executeDeposit` deliberately skips that check (`if (!state.data.isMulticall) { state.validateBorrowATokenCap(); }`), delegating enforcement to the wrapper in `Multicall.multicall`. But the wrapper snapshots `state.data.borrowAToken.balanceOf(address(this))` — the protocol contract's own holdings — for `borrowATokenSupplyBefore`/`After`, not `totalSupply()`. When a user deposits the borrow token, `depositUnderlyingBorrowTokenToVariablePool` mints the scaled aToken to `params.to` (the user), so `totalSupply()` rises but `balanceOf(address(this))` is unchanged. The computed `borrowATokenSupplyIncrease` is therefore `0`, `validateBorrowATokenIncreaseLteDebtTokenDecrease` sees `0 <= debtDecrease` and never reverts, and the cap is never re-checked. (The parameter name `borrowATokenSupply…` versus the `balanceOf(this)` argument actually passed is the tell that the intended metric was total supply.)
- Impact: Any user can exceed `borrowATokenCap` arbitrarily by wrapping a deposit in `multicall([deposit(underlyingBorrowToken, hugeAmount, attacker)])` — the attacker's balance increases, `address(this)` does not, and the cap check passes. The direct-deposit path that would revert with `BORROW_ATOKEN_CAP_EXCEEDED` is defeated, nullifying the admin-configured limit on total borrow-token exposure into the Variable Pool (Aave). Not direct theft, but it removes a safety invariant the admin relies on. Preconditions: the borrow-token deposit path is enabled and the attacker has/obtains the underlying borrow token; no privileged role required.

## Additional findings (single-reviewer)

## Exact-cash credit sales undercharge swap fees
*(Reviewer B only)*
- Location: `src/libraries/AccountingLibrary.sol` : `getCreditAmountIn`; `src/libraries/actions/SellCreditMarket.sol` : `executeSellCreditMarket`.
- Mechanism: For `sellCreditMarket` with `exactAmountIn == false`, `getCreditAmountIn` correctly solves `creditAmountIn` using `PERCENT - swapFeePercent`, but returns `fees = cashAmountOut * swapFeePercent / PERCENT` instead of charging the fee on the gross pre-fee cash amount. The lender then transfers only `cashAmountOut + understatedFees`, while the borrower debt is computed as if the full gross amount was used.
- Impact: Borrower/lender pairs can systematically route trades through exact-cash-out mode to avoid part of the protocol swap fee. Preconditions: nonzero `swapFeeAPR` and use of `sellCreditMarket(..., exactAmountIn: false)`.
- Reviewer note: Reviewer A explicitly walked the swap math (`getCashAmountIn/Out`, `getCreditAmountIn/Out`, fragmentation-fee branches and rounding directions) and assessed it as sound, rounding toward the protocol. The two reviewers disagree on this path.

## Liquidation reward uses borrow-token units as collateral-token units
*(Reviewer B only)*
- Location: `src/libraries/actions/Liquidate.sol` : `executeLiquidate`.
- Mechanism: In profitable liquidations, `liquidatorReward` is computed as `debtPosition.futureValue * liquidationRewardPercent / PERCENT` and added directly to `debtInCollateralToken`. `futureValue` is denominated in borrow-token units while `liquidatorProfitCollateralToken` is denominated in collateral-token units, so the reward is never converted through `debtTokenAmountToCollateralTokenAmount`.
- Impact: With the intended WETH/USDC setup, liquidators receive a near-zero reward instead of the configured collateral-denominated percentage, making liquidations economically unattractive and allowing bad debt to persist. With other decimal/token configurations, the same unit mismatch can overpay liquidators from borrower collateral.
- Reviewer note: Reviewer A examined liquidation economics (`Liquidate`, `SelfLiquidate`, `LiquidateWithReplacement`) and assessed seized-collateral bounding and the protocol/liquidator split as sound, without flagging this unit mismatch. The two reviewers disagree on this path.

## Native ETH balance can be swept by the next ETH depositor
*(Reviewer B only)*
- Location: `src/libraries/actions/Deposit.sol` : `executeDeposit`.
- Mechanism: For ETH/WETH deposits, the function ignores `params.amount` after validation and sets `amount = address(this).balance`, then wraps and mints collateral tokens for that entire balance. Any ETH already sitting in the contract, including forcibly sent ETH, is credited to the current depositor.
- Impact: An attacker can capture any accidental or forcibly sent native ETH by making a minimal valid WETH deposit. Preconditions: the Size contract has a native ETH balance before the attacker's deposit.
- Reviewer note: Reviewer A identified the same `address(this).balance` ETH-wrap behavior but classified it as a "documented footgun" that is not exploitable, reasoning that Size never holds residual ETH between calls. The two reviewers agree on the mechanism but disagree on exploitability.

