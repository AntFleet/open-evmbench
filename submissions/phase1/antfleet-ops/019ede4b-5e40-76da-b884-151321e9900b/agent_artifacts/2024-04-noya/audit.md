# Audit: 2024-04-noya

## MorphoBlue TVL Calculation Adds Debt Instead of Subtracting
- Location: `contracts/connectors/MorphoBlueConnector.sol` : `_getPositionTVL`
- Mechanism: The TVL calculation incorrectly sums the supply amount, borrow amount, and collateral value: `supplyAmount + borrowAmount + convertCToL(...)`. In a margined position, the borrowed amount represents a liability and must be subtracted from the assets to reflect the net equity of the position. 
- Impact: A malicious vault manager can borrow a massive amount of assets from Morpho Blue, which will artificially inflate the vault's reported TVL. This inflated TVL can be weaponized to mint excessive management/performance fees or manipulate the ERC4626 share price to extract underlying funds from passive depositors.

## SNX V3 TVL Calculation Ignores Minted Debt
- Location: `contracts/connectors/SNXConnector.sol` : `_getPositionTVL`
- Mechanism: The TVL calculation only accounts for the deposited and assigned collateral (`totalDeposited + totalAssigned`). It completely ignores any debt (minted sUSD) associated with the account's delegation in the Synthetix V3 pool.
- Impact: A malicious manager can delegate collateral to a pool and mint sUSD (creating protocol debt). The minted sUSD can be swapped for the vault's base token and extracted, while the SNX position's TVL remains unchanged because the liability is never subtracted. This hides the debt, inflates the vault's overall TVL, and allows the manager to drain value at the expense of other shareholders.

## Multiple Connectors: TVL Calculation Reverts on Underwater Positions Causing Vault DoS
- Location: `CompoundConnector.sol`, `DolomiteConnector.sol`, `PrismaConnector.sol`, `SiloConnector.sol` : `_getPositionTVL`
- Mechanism: These connectors calculate TVL by subtracting the debt value from the collateral value (e.g., `positiveBalance - negativeBalance` or `totalDepositAmount - totalBAmount`). If a position becomes underwater (debt > collateral) due to market volatility, liquidation penalties, or oracle lag, the subtraction will underflow and revert in Solidity 0.8.x.
- Impact: An underwater position will cause the `_getPositionTVL` function to revert. Since `AccountingManager.TVL()` iterates through all holding positions to calculate the global TVL, a single revert will cause the entire TVL calculation to fail. This results in a Denial of Service (DoS) for the vault, blocking all user deposits, withdrawals, and fee collections until the position is manually recapitalized.

## AaveConnector: Premature Position Removal on Dust Collateral Hides Debt
- Location: `contracts/connectors/AaveConnector.sol` : `withdrawCollateral`
- Mechanism: The function removes the Aave position from the registry's tracking if `totalCollateralBase <= DUST_LEVEL * 1e7`. Unlike other connectors that check for exact zero balances before removal, this threshold-based removal can occur while the position still holds dust collateral and corresponding dust debt.
- Impact: Once the position is removed from the registry, `TVLHelper.getTVL` will no longer iterate over it, meaning both the remaining collateral and the debt are excluded from the vault's TVL calculation. A manager could exploit this to hide underwater or dust debt positions, artificially inflating the vault's reported TVL and share price.

## BalancerFlashLoan: Broken Token Return Logic Due to Connector Check
- Location: `contracts/connectors/BalancerFlashLoan.sol` : `receiveFlashLoan`
- Mechanism: The contract attempts to retrieve flash-loaned tokens from the `receiver` connector by calling `BaseConnector(receiver).sendTokensToTrustedAddress(...)`. However, `sendTokensToTrustedAddress` internally checks `registry.isAnActiveConnector(vaultId, msg.sender)`. Since `BalancerFlashLoan` is a separate contract and not registered as an active connector, this check fails, the function returns `0`, and the tokens are not transferred back to the flash loan recipient.
- Impact: The flash loan mechanism is fundamentally broken. The tokens will remain stuck in the `receiver` connector, causing the subsequent `safeTransfer` back to the Balancer Vault to revert due to insufficient balance. This renders the flash loan functionality completely unusable and could temporarily trap vault funds if the transaction structure is forced.
