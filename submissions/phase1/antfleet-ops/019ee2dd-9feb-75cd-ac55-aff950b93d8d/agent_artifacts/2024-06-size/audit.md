# Audit: 2024-06-size

 ## Stuck ETH can be stolen through `deposit`
- Location: `src/libraries/actions/Deposit.sol` : `executeDeposit`
- Mechanism: When `msg.value > 0`, `executeDeposit` sets `amount = address(this).balance` and wraps the entire contract ETH balance into WETH before minting collateral tokens. Because every user-facing function is `payable`, ETH can become stuck in the Size contract (e.g., sent to `withdraw`, `buyCreditLimit`, etc., or forced via `selfdestruct`). A subsequent caller can then invoke `deposit` with a small `msg.value` equal to `params.amount`; validation passes, but the caller receives collateral for the full contract balance, stealing ETH left by others.
- Impact: An attacker can mint collateral/WETH for ETH they did not deposit, draining any ETH that becomes stuck in the contract.

## Borrow-aToken cap is bypassed inside `multicall`
- Location: `src/libraries/Multicall.sol` : `multicall`
- Mechanism: `multicall` measures the borrow-aToken “supply” with `state.data.borrowAToken.balanceOf(address(this))` instead of `totalSupply()`. The Size contract itself does not normally hold borrow-aTokens (users do), so this balance is typically zero and does not reflect the actual total supply. Meanwhile, `Deposit.executeDeposit` skips the `borrowATokenCap` check when `state.data.isMulticall` is true. As a result, a multicall that only deposits borrow tokens increases `totalSupply` without ever triggering the cap guard.
- Impact: Users can deposit borrow tokens beyond `riskConfig.borrowATokenCap`, violating the protocol’s supply limit and increasing risk exposure under the intended risk parameters.

## Swap fees are undercharged on fractional `SellCreditMarket` orders
- Location: `src/libraries/AccountingLibrary.sol` : `getCreditAmountIn`
- Mechanism: In the fractionalization branch (`cashAmountOut < maxCashAmountOutFragmentation`), the credit amount is computed correctly, but the swap-fee component of `fees` is calculated as `cashAmountOut * swapFeePercent / PERCENT` instead of `(cashAmountOut + fragmentationFee) * swapFeePercent / (PERCENT - swapFeePercent)`. This returns a lower fee than intended for `SellCreditMarket` calls with `exactAmountIn == false`.
- Impact: The protocol/fee recipient receives less swap fee than the pricing invariant specifies, leading to persistent fee leakage on every fractional sell-credit market order placed with a cash-out amount.

## `updateConfig` cannot increase `crLiquidation`
- Location: `src/libraries/actions/UpdateConfig.sol` : `executeUpdateConfig`
- Mechanism: When updating `crLiquidation`, the code reverts if `params.value >= state.riskConfig.crLiquidation`, i.e., it only permits decreasing the liquidation threshold. It never validates against `crOpening`, so an admin cannot raise `crLiquidation` even when the new value would still satisfy `crLiquidation < crOpening`.
- Impact: Risk parameters can become one-way configurable, preventing the admin from tightening liquidation requirements without first changing other config values, which may delay proper risk management.
