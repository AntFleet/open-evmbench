# Audit: 2023-07-pooltogether

## Anyone can steal accrued yield fees
- Location: `vault/src/Vault.sol` : `mintYieldFee`
- Mechanism: `mintYieldFee` is external and accepts an arbitrary `_recipient`, but it never checks that the caller is authorized or that `_recipient == _yieldFeeRecipient`. Once `_yieldFeeTotalSupply` has accrued through liquidation, any address can reduce that reserve and mint the fee shares to itself.
- Impact: An attacker can mint all accrued yield-fee shares to themselves and redeem/transfer them, stealing fees intended for the configured yield fee recipient.

## Accrued fees can be minted after they are needed as loss buffer
- Location: `vault/src/Vault.sol` : `mintYieldFee`
- Mechanism: The collateralization guard checks only `_totalSupply()` via `_currentExchangeRate()`, ignoring unminted `_yieldFeeTotalSupply`. If the yield vault suffers a loss smaller than the accrued fee reserve, user shares may still appear collateralized, so `mintYieldFee` succeeds even though the fee reserve is already needed to keep the vault whole.
- Impact: The fee reserve can be minted and redeemed after losses, pushing the vault undercollateralized and socializing losses to depositors.

## Anyone can force a depositor into sponsorship delegation
- Location: `vault/src/Vault.sol` : `_sponsor`
- Mechanism: `sponsor` allows the caller to choose any `_receiver`, deposits shares to that receiver, then calls `_twabController.sponsor(_receiver)`. This changes the receiver’s delegation to the sponsorship address without receiver consent. A dust deposit is enough.
- Impact: An attacker can grief any depositor by redirecting their TWAB delegation to sponsorship, removing or reducing their prize eligibility until they notice and redelegate.

## Idle underlying assets can be stolen through deposits
- Location: `vault/src/Vault.sol` : `_deposit`
- Mechanism: `_deposit` treats existing underlying tokens held directly by the vault as payment toward the caller’s deposit. If `_vaultAssets >= _assets`, no tokens are transferred from the caller, yet the vault deposits those idle assets into the yield vault and mints shares to the caller.
- Impact: Any underlying tokens sent directly to the vault, including donations or attempted recapitalization funds, can be captured by the first caller who deposits against that idle balance.

## Liquidators can avoid yield fees by splitting liquidations
- Location: `vault/src/Vault.sol` : `liquidate`
- Mechanism: The fee credited to `_yieldFeeTotalSupply` is rounded down per liquidation: `amountOut / (1 - fee) - amountOut`. Repeated small liquidations can round the fee to zero or materially below the aggregate fee that should have been reserved.
- Impact: A liquidator can split swaps into small chunks and extract yield that should have accrued to the fee recipient, potentially liquidating almost all available yield while paying little or no fee.

## Share amounts are silently truncated to `uint96`
- Location: `vault/src/Vault.sol` : `_transfer`, `_mint`, `_burn`
- Mechanism: ERC20 entrypoints accept `uint256` share amounts, but the vault passes `uint96(_shares)` into `TwabController` without checking bounds. Values above `type(uint96).max` are truncated while events and surrounding accounting use the original `uint256`.
- Impact: Transfers or mints with oversized amounts can succeed while moving only the low 96 bits, breaking ERC20 accounting expectations and enabling over-credit attacks against integrations that trust the requested transfer amount or emitted event.

