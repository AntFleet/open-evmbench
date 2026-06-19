# Audit: 2023-07-pooltogether

## Permissionless fee minting lets anyone steal accrued yield fees
- Location: `vault/src/Vault.sol` : `mintYieldFee`
- Mechanism: `mintYieldFee(uint256 _shares, address _recipient)` is external and has no access control, and it does not require `_recipient == _yieldFeeRecipient`. Any address can call it for any recipient as long as `_shares <= _yieldFeeTotalSupply`. The function then decrements the accrued fee balance and mints real vault shares to the attacker-controlled recipient.
- Impact: An attacker can steal all accrued yield fees by calling `mintYieldFee(yieldFeeTotalSupply(), attacker)`, then redeem or transfer those shares like normal vault shares.

## Accrued fee buffer can be minted even when needed to keep the vault solvent
- Location: `vault/src/Vault.sol` : `mintYieldFee`, `_isVaultCollateralized`, `_currentExchangeRate`
- Mechanism: `mintYieldFee` only checks `_requireVaultCollateralized()`, but `_currentExchangeRate()` computes collateralization using `_totalSupply()` and ignores `_yieldFeeTotalSupply`. This means the vault can appear collateralized for already-minted shares while accrued fee shares are the only buffer covering a yield-vault loss. `mintYieldFee` can then mint the full `_yieldFeeTotalSupply`, pushing the vault below 1:1 collateralization after the mint.
- Impact: After a partial loss in the underlying yield vault, an attacker can mint accrued fee shares to themselves and turn what should have been absorbed by the fee buffer into a loss for depositors.

## Direct underlying balances can be captured by the next depositor
- Location: `vault/src/Vault.sol` : `_deposit`
- Mechanism: `_deposit` treats any underlying asset balance already held by the vault as if it were supplied by the current depositor. If `_assets <= IERC20(asset()).balanceOf(address(this))`, it performs no `transferFrom` from the caller, but still deposits `_assets` into the yield vault and mints `_shares` to `_receiver`.
- Impact: Any underlying tokens sitting directly in the vault, from accidental transfers or unswept protocol balances, can be stolen by the first caller who deposits the same amount. The attacker receives fully backed vault shares without providing the assets.

