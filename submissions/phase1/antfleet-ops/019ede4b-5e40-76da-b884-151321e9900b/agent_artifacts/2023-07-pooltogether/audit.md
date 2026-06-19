# Audit: 2023-07-pooltogether

## Unauthorized Yield Fee Minting
- Location: `Vault.sol` : `mintYieldFee`
- Mechanism: The `mintYieldFee` function accepts an arbitrary `_recipient` address as a parameter instead of using the stored `_yieldFeeRecipient` state variable. Furthermore, there is no access control restricting who can call this function. The function blindly mints the requested amount of yield fee shares to the user-supplied `_recipient` address.
- Impact: Any external user can call `mintYieldFee` and pass their own address as the `_recipient`, allowing them to steal 100% of the accrued yield fees that were intended for the protocol or vault owner. This results in a direct and total loss of yield fee funds.

## Denial of Service via Division by Zero in Liquidation
- Location: `Vault.sol` : `liquidate` / `_setYieldFeePercentage`
- Mechanism: The `_setYieldFeePercentage` function allows the owner to set the yield fee percentage to exactly `FEE_PRECISION` (1e9, representing 100%) because it only checks `yieldFeePercentage_ > FEE_PRECISION`. When `_yieldFeePercentage` equals `FEE_PRECISION`, the denominator in the `liquidate` function's fee calculation `(FEE_PRECISION - _yieldFeePercentage)` evaluates to zero. Because Solidity 0.8.x natively reverts on division by zero, the transaction will panic.
- Impact: If the owner (maliciously or accidentally) sets the yield fee to 100%, the `liquidate` function becomes permanently bricked. This halts all yield liquidation, completely breaking the vault's core mechanism of converting yield into prize tokens for depositors.

## Apples-to-Oranges Comparison Causes Stuck Idle Assets
- Location: `Vault.sol` : `liquidate`
- Mechanism: During liquidation, the contract attempts to sweep idle underlying assets into the yield vault using the condition `if (_vaultAssets != 0 && _amountOut >= _vaultAssets)`. However, `_amountOut` represents the amount of vault *shares* to be minted to the liquidator, while `_vaultAssets` represents the raw balance of underlying *assets* (e.g., USDC) sitting idle in the vault. Comparing share units to asset units is a fundamental logic error.
- Impact: If the numerical value of the shares being minted is less than the idle asset balance (which is highly likely depending on the exchange rate and asset decimals), the condition fails and the idle assets are not swept into the yield vault. This causes underlying assets to remain stuck in the vault contract where they do not generate yield, artificially reducing the prize pool size over time.
