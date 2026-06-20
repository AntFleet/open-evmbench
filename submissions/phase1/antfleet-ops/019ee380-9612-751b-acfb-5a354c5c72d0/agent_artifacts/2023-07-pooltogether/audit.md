# Audit: 2023-07-pooltogether

Below are the genuine security vulnerabilities I found in this codebase.

## Yield fee can be stolen by anyone via arbitrary recipient
- Location: `vault/src/Vault.sol` : `mintYieldFee`
- Mechanism: `mintYieldFee(uint256 _shares, address _recipient)` is declared `external` with no access control and lets the caller name an arbitrary `_recipient`. It only checks that the vault is collateralized and that `_shares <= _yieldFeeTotalSupply`, then does `_yieldFeeTotalSupply -= _shares; _mint(_recipient, _shares);`. The accrued yield fee (built up in `_yieldFeeTotalSupply` during every `liquidate`) is intended for `_yieldFeeRecipient`, but nothing enforces `_recipient == _yieldFeeRecipient` or restricts the caller.
- Impact: Any external account can call `mintYieldFee(yieldFeeTotalSupply(), attacker)` and mint all accrued yield-fee shares to itself, then redeem them for underlying assets. The protocol's entire yield fee is directly stealable. Because `_totalShares()` is unchanged (it moves `_shares` from `_yieldFeeTotalSupply` into `_totalSupply`), collateralization checks still pass, so the theft is silent.

## Depositor mints shares without supplying backing when loose assets are present
- Location: `vault/src/Vault.sol` : `_deposit`
- Mechanism: To optimize, `_deposit` reads `_vaultAssets = _asset.balanceOf(address(this))` and only pulls funds from the caller when `_assets > _vaultAssets`. When the vault already holds at least `_assets` of loose underlying (`_vaultAssets >= _assets`), the `if (_assets > _vaultAssets)` branch is skipped entirely — no `transferFrom` occurs — yet the code still calls `_yieldVault.deposit(_assets, ...)` (spending the vault's own loose balance) and `_mint(_receiver, _shares)`. Even in the partial case the caller is only charged `_assets - _vaultAssets`. The "only transfer the difference" logic implicitly assumes any loose balance belongs to the depositor, which is not enforced.
- Impact: Any underlying assets sitting loose in the vault (e.g. tokens accidentally transferred in, or left un-swept) can be captured for free by the next depositor, who receives full-value shares while paying little or nothing. An attacker can monitor for mis-sent funds and front-run a deposit to mint shares fully (or partially) backed by someone else's assets, then redeem them.

## Loose-asset sweep in `liquidate` is gated on a units-mismatched comparison
- Location: `vault/src/Vault.sol` : `liquidate`
- Mechanism: After contributing prize tokens and computing the fee, the function attempts to move idle underlying into the yield vault: `if (_vaultAssets != 0 && _amountOut >= _vaultAssets) { _yieldVault.deposit(_vaultAssets, address(this)); }`. Here `_amountOut` is a quantity of **vault shares** being minted to the liquidator, while `_vaultAssets` is a balance of **underlying assets** — two unrelated units. The sweep therefore fires (or fails to fire) based on a meaningless comparison.
- Impact: Idle underlying assets are left uninvested in the vault whenever `_amountOut < _vaultAssets`, and conversely the branch can deposit at arbitrary times. Combined with the `_deposit` issue above, these stranded loose assets become capturable by a subsequent depositor rather than being safely placed in the yield vault, compounding the loose-asset exposure.

The remaining functions (`claimPrizes`/`_claimPrize` hooks, `withdraw`/`redeem`, exchange-rate handling) follow the ERC4626/TWAB patterns correctly; the hook calls in `_claimPrize` only affect the winner's own prize and the burn-before-transfer ordering in `_withdraw` is reentrancy-safe.

