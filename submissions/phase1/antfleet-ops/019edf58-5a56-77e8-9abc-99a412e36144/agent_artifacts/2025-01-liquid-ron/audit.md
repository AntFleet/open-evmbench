# Audit: 2025-01-liquid-ron

## Broken `onlyOperator` modifier — operators can never call restricted functions

- Location: `LiquidRon.sol` : `onlyOperator` modifier
- Mechanism: The modifier reads `if (msg.sender != owner() || operator[msg.sender]) revert`. The boolean logic is inverted: it reverts whenever the caller is **not** the owner **or** is an operator. Consequently a designated operator (who is not the owner) always hits `true || true → revert` and can never call any `onlyOperator` function. The intended check should require the caller to be **neither** owner nor operator before reverting (i.e. `&&` / negated OR).
- Impact: All operator-gated functions (`harvest`, `harvestAndDelegateRewards`, `delegateAmount`, `redelegateAmount`, `undelegateAmount`, `finaliseRonRewardsForEpoch`) are callable **only** by `owner`. The entire operator role is non-functional; any off-chain operator bot or delegated manager is permanently locked out, breaking the staking/reward/withdrawal workflow.

## Accrued `operatorFeeAmount` is not deducted from `totalAssets`

- Location: `LiquidRon.sol` : `totalAssets` / `harvest` / `fetchOperatorFee`
- Mechanism: When rewards are harvested, the full harvested RON is wrapped and sent to the vault, increasing `super.totalAssets()` (the vault's WRON balance). Simultaneously `operatorFeeAmount` is incremented by the fee share. However `totalAssets()` never subtracts `operatorFeeAmount`, so the accrued operator fee is counted as if it were shareholder assets. The fee liability remains on the books until `fetchOperatorFee` unwraps and sends it out, at which point `totalAssets` drops.
- Impact: Between every harvest and the corresponding `fetchOperatorFee` call the share price is artificially inflated by the accrued fee. Any user who deposits before and redeems before the fee is pulled extracts a portion of the operator's fee; remaining shareholders suffer a corresponding share-price drop once `fetchOperatorFee` executes. This is an accounting error that lets attackers steal accrued operator fees by front-running fee withdrawal.

## `harvestAndDelegateRewards` accrues fees against illiquid delegated stake

- Location: `LiquidRon.sol` : `harvestAndDelegateRewards` ; `LiquidProxy.sol` : `harvestAndDelegateRewards`
- Mechanism: `LiquidProxy.harvestAndDelegateRewards` delegates the claimed rewards to a validator and returns the claimed amount; no RON/WRON is sent back to the vault. `LiquidRon.harvestAndDelegateRewards` still increments `operatorFeeAmount` by `harvestedAmount * operatorFee / BIPS`. The corresponding assets are now locked in staking (counted in `getTotalStaked`), not as liquid WRON in the vault.
- Impact: `fetchOperatorFee` calls `_withdrawRONTo(feeRecipient, amount)`, which unwraps WRON from the vault's liquid balance. For fees accrued via `harvestAndDelegateRewards` there is no corresponding liquid WRON, so the call either reverts (if the vault lacks sufficient WRON) or silently consumes WRON that belongs to depositors / other harvested rewards, reducing `totalAssets` and diluting remaining shareholders. The operator fee liability is backed by the wrong pool of assets.
