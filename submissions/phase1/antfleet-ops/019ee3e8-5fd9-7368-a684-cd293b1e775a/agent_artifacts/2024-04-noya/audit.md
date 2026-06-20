# Audit: 2024-04-noya

## AccountingManager 
- Location: `AccountingManager.sol` : `initialize`
- Mechanism: In the `initialize` function, the `valueOracle` variable is set to an oracle contract that provides the value of the vault's holdings. However, there is no validation to ensure that this oracle contract is trustworthy and correctly configured.
- Impact: An attacker could manipulate the price of the vault's holdings by controlling the value oracle contract, allowing them to drain the vault by minting an arbitrarily large number of shares.

## AccountingManager 
- Location: `AccountingManager.sol` : `updateValueOracle`
- Mechanism: The `updateValueOracle` function updates the `valueOracle` contract address and does not perform any additional validation.
- Impact: A malicious maintainer could update the `valueOracle` contract address to a fake contract that always returns a high valuation, allowing the maintainer to drain the vault's deposits.

## AccountingManager 
- Location: `AccountingManager.sol` : `executeDeposit`
- Mechanism: The `executeDeposit` function calls the `addLiquidity` function of the `connector` contract, but it does not verify that the `connector` contract is correctly configured and secure.
- Impact: An attacker could manipulate the `connector` contract to drain the vault's liquidity or drain user deposits.

## BaseConnector 
- Location: `BaseConnector.sol` : `sendTokensToTrustedAddress`
- Mechanism: The `sendTokensToTrustedAddress` function sends tokens to a trusted address without verifying that the recipient is actually trusted.
- Impact: A malicious connector could drain the vault's liquidity or steal user deposits by manipulating the `trustedTokens` mapping.

## Registry 
- Location: `PositionRegistry.sol` : `addPool` and `addToken`
- Mechanism: These functions do not perform any additional validation on the pool and token contracts, allowing a malicious attacker to add malicious or untrusted contracts to the registry.
- Impact: An attacker could add a malicious pool or token contract to the registry, allowing them to drain the vault's liquidity or deposits.

## Registry 
- Location: `PositionRegistry.sol` : `updateTokenInRegistry`
- Mechanism: The `updateTokenInRegistry` function adds tokens to the registry without validating the tokens.
- Impact: An attacker could add untrusted or malicious tokens to the registry, allowing them to drain the vault's liquidity or deposits.

## Registry 
- Location: `PositionRegistry.sol` : `isPositionTrustedForConnector` and `isAddressTrusted`
- Mechanism: These functions rely on the `trustedPositionsBP` mapping to determine if a position is trusted, but this mapping can be manipulated by a malicious maintainer.
- Impact: A malicious maintainer could update the `trustedPositionsBP` mapping to allow untrusted positions or addresses, allowing them to drain the vault's liquidity or deposits.

## AaveConnector 
- Location: `AaveConnector.sol` : `supply` and `withdraw` functions
- Mechanism: The `supply` and `withdraw` functions do not perform any validation on the Aave contract calls, allowing an attacker to manipulate the Aave contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the Aave contract state.

## AerodromeConnector 
- Location: `AerodromeConnector.sol` : `addLiquidity` and `removeLiquidityFromAerodromePool` functions
- Mechanism: The `addLiquidity` and `removeLiquidityFromAerodromePool` functions do not perform any validation on the Aerodrome contract calls, allowing an attacker to manipulate the Aerodrome contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the Aerodrome contract state.

## BalancerConnector 
- Location: `BalancerConnector.sol` : `openPosition` and `decreasePosition` functions
- Mechanism: The `openPosition` and `decreasePosition` functions do not perform any validation on the Balancer contract calls, allowing an attacker to manipulate the Balancer contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the Balancer contract state.

## CurveConnector 
- Location: `CurveConnector.sol` : `depositIntoGauge` and `withdrawFromGauge` functions
- Mechanism: The `depositIntoGauge` and `withdrawFromGauge` functions do not perform any validation on the Curve contract calls, allowing an attacker to manipulate the Curve contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the Curve contract state.

## CompoundConnector 
- Location: `CompoundConnector.sol` : `supply`, `withdraw`, `withdrawOrBorrow`, `repay`, and `claimRewards` functions
- Mechanism: The `supply`, `withdraw`, `withdrawOrBorrow`, `repay`, and `claimRewards` functions do not perform any validation on the Compound contract calls, allowing an attacker to manipulate the Compound contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the Compound contract state.

## DolomiteConnector 
- Location: `DolomiteConnector.sol` : `deposit`, `withdraw`, `openBorrowPosition`, `closeBorrowPosition`, `transferBetweenAccounts`, `openTrove`, and `addColl` functions
- Mechanism: The `deposit`, `withdraw`, `openBorrowPosition`, `closeBorrowPosition`, `transferBetweenAccounts`, `openTrove`, and `addColl` functions do not perform any validation on the Dolomite contract calls, allowing an attacker to manipulate the Dolomite contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the Dolomite contract state.

## FraxConnector 
- Location: `FraxConnector.sol` : `borrowAndSupply` and `withdraw` functions
- Mechanism: The `borrowAndSupply` and `withdraw` functions do not perform any validation on the Frax contract calls, allowing an attacker to manipulate the Frax contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the Frax contract state.

## Gearboxv3 
- Location: `Gearboxv3.sol` : `openAccount`, `closeAccount`, `executeCommands` functions
- Mechanism: The `openAccount`, `closeAccount`, and `executeCommands` functions do not perform any validation on the Gearbox contract calls, allowing an attacker to manipulate the Gearbox contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the Gearbox contract state.

## LidoConnector 
- Location: `LidoConnector.sol` : `deposit`, `requestWithdrawals`, `claimWithdrawal` functions
- Mechanism: The `deposit`, `requestWithdrawals`, and `claimWithdrawal` functions do not perform any validation on the Lido contract calls, allowing an attacker to manipulate the Lido contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the Lido contract state.

## MaverickConnector 
- Location: `MaverickConnector.sol` : `addLiquidityInMaverickPool` and `removeLiquidityFromMaverickPool` functions
- Mechanism: The `addLiquidityInMaverickPool` and `removeLiquidityFromMaverickPool` functions do not perform any validation on the Maverick contract calls, allowing an attacker to manipulate the Maverick contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the Maverick contract state.

## MorphoBlueConnector 
- Location: `MorphoBlueConnector.sol` : `supply`, `borrow`, `withdraw`, `repay` functions
- Mechanism: The `supply`, `borrow`, `withdraw`, and `repay` functions do not perform any validation on the Morpho contract calls, allowing an attacker to manipulate the Morpho contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the Morpho contract state.

## PancakeswapConnector 
- Location: `PancakeswapConnector.sol` : `sendPositionToMasterChef` and `withdraw` functions
- Mechanism: The `sendPositionToMasterChef` and `withdraw` functions do not perform any validation on the Pancakeswap contract calls, allowing an attacker to manipulate the Pancakeswap contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the Pancakeswap contract state.

## PendleConnector 
- Location: `PendleConnector.sol` : `supply`, `mintPTAndYT`, `depositIntoMarket`, `depositIntoPenpie`, `withdrawFromPenpie`, `swap`, `burnLP`, `decreasePosition`, and `claimRewards` functions
- Mechanism: The `supply`, `mintPTAndYT`, `depositIntoMarket`, `depositIntoPenpie`, `withdrawFromPenpie`, `swap`, `burnLP`, `decreasePosition`, and `claimRewards` functions do not perform any validation on the Pendle contract calls, allowing an attacker to manipulate the Pendle contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the Pendle contract state.

## PrismaConnector 
- Location: `PrismaConnector.sol` : `openTrove`, `addColl`, `adjustTrove`, and `closeTrove` functions
- Mechanism: The `openTrove`, `addColl`, `adjustTrove`, and `closeTrove` functions do not perform any validation on the Prisma contract calls, allowing an attacker to manipulate the Prisma contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the Prisma contract state.

## BalancerFlashLoan 
- Location: `BalancerFlashLoan.sol` : `makeFlashLoan` and `receiveFlashLoan` functions
- Mechanism: The `makeFlashLoan` and `receiveFlashLoan` functions do not perform any validation on the flash loan contract calls, allowing an attacker to manipulate the flash loan contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the flash loan contract state.

## SiloConnector 
- Location: `SiloConnector.sol` : `deposit`, `withdraw`, `borrow`, and `repay` functions
- Mechanism: The `deposit`, `withdraw`, `borrow`, and `repay` functions do not perform any validation on the Silo contract calls, allowing an attacker to manipulate the Silo contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the Silo contract state.

## StargateConnector 
- Location: `StargateConnector.sol` : `depositIntoStargatePool` and `withdrawFromStargatePool` functions
- Mechanism: The `depositIntoStargatePool` and `withdrawFromStargatePool` functions do not perform any validation on the Stargate contract calls, allowing an attacker to manipulate the Stargate contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the Stargate contract state.

## UNIv3Connector 
- Location: `UNIv3Connector.sol` : `openPosition` and `collectAllFees` functions
- Mechanism: The `openPosition` and `collectAllFees` functions do not perform any validation on the UNIv3 contract calls, allowing an attacker to manipulate the UNIv3 contract state.
- Impact: An attacker could drain the vault's liquidity or deposits by manipulating the UNIv3 contract state.
