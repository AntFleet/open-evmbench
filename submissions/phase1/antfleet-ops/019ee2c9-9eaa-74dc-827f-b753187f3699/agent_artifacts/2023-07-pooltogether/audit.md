# Audit: 2023-07-pooltogether

## Unrestricted minting of protocol fee shares
- Location: `vault/src/Vault.sol` : `mintYieldFee`
- Mechanism: `liquidate()` accrues protocol fees by increasing `_yieldFeeTotalSupply`, but `mintYieldFee()` is callable by anyone and does not check `msg.sender` against `yieldFeeRecipient()` or `owner()`. It also ignores the configured `_yieldFeeRecipient` entirely and lets the caller choose any `_recipient`. As long as the vault is collateralized, any external account can call `mintYieldFee(_yieldFeeTotalSupply, attacker)` and convert all accrued fee supply into real vault shares for itself.
- Impact: An attacker can steal all accumulated protocol/yield fees, permanently diverting shares that were supposed to belong to the configured fee recipient.

## Free share minting against vault-held idle assets
- Location: `vault/src/Vault.sol` : `_deposit` / `deposit` / `mint`
- Mechanism: `_currentExchangeRate()` prices shares using only `_yieldVault.maxWithdraw(address(this))`, so underlying tokens sitting directly on the Vault are excluded from share pricing. But `_deposit()` explicitly reuses those direct vault-held assets: if `_assets <= IERC20(asset()).balanceOf(address(this))`, it skips `transferFrom` entirely, deposits the already-held tokens into the yield vault, and still mints fresh shares to the caller. That means the next depositor can receive shares as if they had supplied assets even though the Vault funded the deposit from its pre-existing balance.
- Impact: Any idle underlying sitting on the Vault can be stolen by an arbitrary depositor, who can mint redeemable shares without paying. This captures mistakenly transferred assets, dust, or any residual underlying left on the contract.

## Partial liquidation can force artificial undercollateralization and brick core flows
- Location: `vault/src/Vault.sol` : `liquidate` / `_currentExchangeRate` / `availableYieldBalance`
- Mechanism: `availableYieldBalance()` and `_liquidatableBalanceOf()` count direct vault-held underlying as available yield via `_totalAssets()`, but `_currentExchangeRate()` ignores those same assets and only looks at what is withdrawable from `_yieldVault`. In `liquidate()`, direct vault-held assets are only swept into the yield vault when `_amountOut >= _vaultAssets`; for a smaller liquidation, the idle assets remain in the Vault while `_mint(_account, _amountOut)` increases share supply. After that mint, the recalculated exchange rate drops below 1 because the new shares are measured only against yield-vault assets, so `_isVaultCollateralized()` becomes false even though the contract still holds enough total underlying.
- Impact: Anyone who can route a small liquidation through the configured `LiquidationPair` can push the Vault into a stuck undercollateralized state whenever the Vault holds idle underlying. That disables new deposits, mints, further liquidations, and fee minting, while the stranded direct-held assets are excluded from the normal redemption accounting path.

