# Audit: 2023-07-pooltogether

 ## Unrestricted minting of yield fee shares
- Location: `Vault.sol` : `mintYieldFee`
- Mechanism: `mintYieldFee` is an external function with no access control and takes a caller-supplied `_recipient`. It only verifies that the requested `_shares` do not exceed `_yieldFeeTotalSupply` and that the vault is collateralized, then mints those shares to `_recipient` and decrements the fee supply. There is no requirement that the caller be the configured `_yieldFeeRecipient` or that `_recipient` be the fee recipient.
- Impact: Any address can steal the entire accrued yield fee by calling `mintYieldFee(_yieldFeeTotalSupply, attacker)`. The attacker receives fee-backed vault shares that can be redeemed for underlying assets, draining value that should belong to the yield fee recipient.

## Exchange rate misreports full collateralization when no assets are withdrawable
- Location: `Vault.sol` : `_currentExchangeRate`
- Mechanism: The function returns `_assetUnit` whenever `_totalSupplyAmount == 0` or `_withdrawableAssets == 0`. The second case means that if shares exist but `_yieldVault.maxWithdraw(address(this))` returns `0` (empty/compromised/paused yield vault, or a malicious yield vault), `_currentExchangeRate()` reports `1` rather than a rate reflecting zero backing.
- Impact: `_isVaultCollateralized()` becomes `true`, so `maxDeposit`/`maxMint` are non-zero and the vault accepts new deposits while it has no withdrawable assets. New deposits back existing unbacked shares; if withdrawals are at all possible, earlier depositors can drain the new funds, otherwise new depositors lose assets in an insolvent vault.

## Deposits can be funded from the vault’s own idle balance
- Location: `Vault.sol` : `_deposit`
- Mechanism: `_deposit` reads `_vaultAssets = _asset.balanceOf(address(this))` and transfers from the caller only when `_assets > _vaultAssets`, sending just `_assets - _vaultAssets`. When the vault already holds the requested amount (e.g. from direct transfers, donations, or un-deposited sweep), the caller pays nothing, yet the vault deposits those existing assets into `_yieldVault` and mints new shares to `_receiver`.
- Impact: A user can repeatedly mint shares for free whenever the vault has an underlying-asset balance, capturing vault-held assets/yield and diluting existing shareholders. This breaks the ERC-4626 invariant that a deposit must transfer assets from the caller.

## Liquidation mints silently truncate shares to `uint96`
- Location: `Vault.sol` : `_mint` (reachable from `liquidate`)
- Mechanism: `_mint` casts `_shares` to `uint96` with `uint96(_shares)` before calling `_twabController.mint`. Deposit and mint flows are bounded by `maxMint`/`maxDeposit` returning `type(uint96).max`, but `liquidate` accepts an arbitrary `_amountOut` chosen by the liquidation pair, and a liquidatable yield larger than `type(uint96).max` will silently drop the high-order bits.
- Impact: Share accounting diverges from the amount the liquidator paid for. `_totalSupply()` becomes inconsistent with `_yieldFeeTotalSupply` and the vault’s real liabilities, corrupting the exchange rate and liquidation math.

## 100% yield fee bricks all liquidations
- Location: `Vault.sol` : `_setYieldFeePercentage` / `liquidate`
- Mechanism: `_setYieldFeePercentage` reverts only when `yieldFeePercentage_ > FEE_PRECISION`, so `_yieldFeePercentage == FEE_PRECISION` (100%) is allowed. With a 100% fee, `_liquidatableBalanceOf` returns zero and any non-zero `liquidate` call fails; if execution reached the fee formula it would also divide by `FEE_PRECISION - _yieldFeePercentage == 0`.
- Impact: An owner can accidentally or maliciously set a 100% yield fee, freezing all yield liquidation and stopping the conversion of yield into prize tokens for the prize pool.

## Unlimited underlying-asset allowance granted to the liquidation pair
- Location: `Vault.sol` : `setLiquidationPair`
- Mechanism: When a new liquidation pair is set, the vault calls `_asset.safeApprove(address(liquidationPair_), type(uint256).max)`. The pair’s only legitimate role is to call `liquidate` and receive vault shares; it never needs to spend the vault’s underlying asset, yet it receives an unlimited allowance.
- Impact: If the liquidation pair contract is compromised, upgraded maliciously, or contains a bug, it can transfer the vault’s entire underlying-asset balance to any address, draining depositors.
