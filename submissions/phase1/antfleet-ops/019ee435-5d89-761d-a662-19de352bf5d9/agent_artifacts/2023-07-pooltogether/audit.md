# Audit: 2023-07-pooltogether

## Unsafe `uint96` share downcast allows under-burning and vault drain

- Location: `vault/src/Vault.sol` : `_burn` / `_transfer` / `_mint`
- Mechanism: Vault share amounts are handled as `uint256`, but TWAB accounting is called with `uint96(_shares)` without a checked cast. `maxDeposit` and `maxMint` cap only a single operation, not the resulting account balance, while `TwabController` stores balances wider than `uint96`. A user can accumulate more than `type(uint96).max` shares, then redeem/withdraw an amount whose `_shares` value is silently truncated before `TwabController.burn`.
- Impact: An attacker can withdraw assets for the full `uint256` share amount while burning only the truncated `uint96` amount, leaving residual shares that can be used to withdraw other users’ assets.

## Anyone can steal accrued yield fees

- Location: `vault/src/Vault.sol` : `mintYieldFee`
- Mechanism: `mintYieldFee(uint256 _shares, address _recipient)` is external, has no access control, and does not require `_recipient` to equal the configured `_yieldFeeRecipient`. Any caller can mint up to `_yieldFeeTotalSupply` to an arbitrary address.
- Impact: An attacker can call `mintYieldFee(yieldFeeTotalSupply(), attacker)` and receive all accrued protocol fee shares, then redeem or transfer them as normal vault shares.

## Fee buffer can be minted while needed for solvency

- Location: `vault/src/Vault.sol` : `mintYieldFee` / `_currentExchangeRate`
- Mechanism: `mintYieldFee` only checks `_requireVaultCollateralized()`, but `_currentExchangeRate()` computes collateralization against `_totalSupply()` and ignores `_yieldFeeTotalSupply`. The fee supply is otherwise counted in `_totalShares()` as a buffer against losses. If assets cover minted user shares but not user shares plus accrued fee shares, the function still allows the fee supply to be minted.
- Impact: An attacker can mint the fee buffer into real shares after a partial yield-vault loss, pushing the vault undercollateralized and shifting losses onto depositors.

## Vault-held underlying can be captured by the next depositor

- Location: `vault/src/Vault.sol` : `_deposit`
- Mechanism: `_deposit` checks `IERC20(asset()).balanceOf(address(this))` and, if the vault already holds enough underlying, skips `transferFrom` from the depositor. It then deposits `_assets` into the yield vault and mints shares to the caller. Direct vault-held assets are not priced into `_currentExchangeRate()`, so the caller receives shares as if they supplied the assets themselves.
- Impact: Any underlying tokens sitting directly in the Vault, from accidental transfers or stranded balances, can be stolen by the first account that deposits the same amount.

## Partial liquidation of idle underlying can brick the vault

- Location: `vault/src/Vault.sol` : `liquidate`
- Mechanism: `availableYieldBalance()` includes direct vault-held underlying through `_totalAssets()`, but `_currentExchangeRate()` only uses `_yieldVault.maxWithdraw(address(this))`. During liquidation, direct underlying is swept into the yield vault only when `_amountOut >= _vaultAssets`. A liquidation for less than the idle balance mints new shares while leaving the backing assets outside the exchange-rate calculation.
- Impact: A liquidator can make the vault appear undercollateralized even when total assets are sufficient, disabling deposits, mints, further liquidations, and fee minting until the accounting state is repaired.

## Anyone can force a user into sponsorship delegation

- Location: `vault/src/Vault.sol` : `_sponsor`
- Mechanism: `sponsor` lets the caller choose any `_receiver`. After depositing, `_sponsor` calls `_twabController.sponsor(_receiver)`, which delegates that receiver’s entire vault balance to the sponsorship address. There is no requirement that `_receiver` consent or that `msg.sender == _receiver`.
- Impact: An attacker can deposit a dust amount for a victim and force the victim’s TWAB delegation to the sponsorship address, removing their prize-winning eligibility until they notice and re-delegate.

