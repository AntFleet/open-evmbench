# Audit: 2024-04-noya

# Security Audit Report

## Access Control Logic Error in Registry Modifiers
- Location: `contracts/accountingManager/Registry.sol` : `onlyVaultMaintainer`, `onlyVaultMaintainerWithoutTimeLock`, `onlyVaultGoverner`
- Mechanism: The modifiers use `||` (OR) instead of `&&` (AND) in the access check. For example: `if (msg.sender != vaults[_vaultId].maintainer || hasRole(EMERGENCY_ROLE, msg.sender) == false)`. This reverts unless the caller is **both** the vault maintainer **and** an emergency role holder. The intent (allowing either the maintainer or emergency role) requires `&&`.
- Impact: Functions protected by these modifiers — `addConnector`, `updateConnectorTrustedTokens`, `removeTrustedPosition`, `changeVaultAddresses`, `addTrustedPosition` — become callable only by an address that simultaneously holds both the vault-specific governance role and the global emergency role. This effectively breaks the intended governance model and could lock out legitimate operators from managing vaults, connectors, and positions.

## MorphoBlueConnector TVL Adds Debt Instead of Subtracting
- Location: `contracts/connectors/MorphoBlueConnector.sol` : `_getPositionTVL`
- Mechanism: The TVL is computed as `supplyAmount + borrowAmount + convertCToL(pos.collateral, ...)`, where `borrowAmount` is the outstanding debt (converted from borrow shares). The debt should be **subtracted** from the sum of supply and collateral, not added.
- Impact: The vault's TVL is inflated by twice the borrow amount. This causes `previewDeposit`/`previewRedeem` to mint/redeem shares at incorrect prices, allowing depositors to receive more shares than they should and causing value dilution to existing shareholders. Fee calculations based on profit/TVL are also corrupted.

## SNXConnector Double-Counts Assigned Collateral
- Location: `contracts/connectors/SNXConnector.sol` : `_getPositionTVL`
- Mechanism: The function computes `tvl = _getValue(collateralType, base, totalDeposited + totalAssigned)`. In Synthetix V3, `totalDeposited` already includes `totalAssigned` (the delegated portion) plus `totalLocked`. Adding `totalAssigned` again double-counts the delegated collateral.
- Impact: The position's TVL is overstated, inflating the vault's total assets. This leads to incorrect share pricing, unjustified fee accrual, and potential value extraction by new depositors at the expense of existing shareholders.

## DolomiteConnector Removes Position When Opening Borrow Position
- Location: `contracts/connectors/DolomiteConnector.sol` : `openBorrowPosition`
- Mechanism: `openBorrowPosition` calls `registry.updateHoldingPosition(..., true)` with `removePosition = true`. When opening a borrow position, the holding position should be added/updated (passing `false`), not removed.
- Impact: The borrow position is immediately removed from the registry after creation, so its collateral and debt are not included in TVL calculations. This causes the vault to underreport its assets, leading to incorrect share pricing and potentially allowing withdrawals that exceed the true asset backing.

## MaverickConnector Missing Reward Token Registry Update
- Location: `contracts/connectors/MaverickConnector.sol` : `claimBoostedPositionRewards`
- Mechanism: The function claims rewards via `rewardContract.getReward(...)` but never calls `_updateTokenInRegistry(rewardToken)` for any of the earned reward tokens. Other connectors (e.g., CurveConnector, StargateConnector, PancakeswapConnector) consistently update the registry after claiming rewards.
- Impact: Claimed reward tokens are not tracked in the vault's TVL or token registry. These tokens sit in the connector contract unaccounted for, leading to undervalued TVL and incorrect share pricing. The rewards may also become difficult to recover since no holding position is recorded for them.

## TVL Underflow in Connectors with Debt Positions
- Location: `contracts/connectors/CompoundConnector.sol` : `_getPositionTVL`, `contracts/connectors/PrismaConnector.sol` : `_getPositionTVL`
- Mechanism: CompoundConnector computes `uint256 balance = positiveBalance - negativeBalance` and PrismaConnector computes `_getValue(collateral, base, collateralBalance) - _getValue(debTtoken, base, debtBalance)`. Both use unsigned subtraction. If the position becomes underwater (debt exceeds collateral), these expressions revert due to underflow.
- Impact: If any debt position becomes underwater (e.g., due to market movement or liquidation), the entire `TVL()` call reverts, blocking all deposits, withdrawals, share calculations, and fee distributions across the entire vault until the position is manually resolved.
