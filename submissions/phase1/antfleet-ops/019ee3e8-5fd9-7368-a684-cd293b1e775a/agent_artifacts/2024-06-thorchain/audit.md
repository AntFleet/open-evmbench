# Audit: 2024-06-thorchain

# Reentrancy Vulnerability in AvaxAggregator
### <Reentrancy Vulnerability>
- Location: `avax/src/contracts/AvaxAggregator.sol` : `swapIn` function
- Mechanism: The `swapIn` function calls `ISwapRouter(swapRouter).swapExactTokensForAVAX` and then `IRouter(tcRouter).depositWithExpiry`. If the contract at `tcRouter` is malicious, it can cause a reentrancy attack by calling back into the `swapIn` function or another function that calls `depositWithExpiry`.
- Impact: An attacker can drain the funds of the `AvaxAggregator` contract by repeatedly calling `depositWithExpiry` and causing the contract to transfer more funds than intended.

# Reentrancy Vulnerability in AvaxRouter
### <Reentrancy Vulnerability>
- Location: `avax/src/contracts/AvaxRouter.sol` : `transferOut` and `transferOutAndCall` functions
- Mechanism: The `transferOut` and `transferOutAndCall` functions call `asset.call` and `target.call` respectively, which can lead to a reentrancy attack if the contract at `asset` or `target` is malicious.
- Impact: An attacker can drain the funds of the `AvaxRouter` contract by repeatedly calling `transferOut` or `transferOutAndCall` and causing the contract to transfer more funds than intended.

# Unprotected Function in EvilCallback
### <Unprotected Function>
- Location: `chain/ethereum/contracts/EvilCallback.sol` : `receive` function
- Mechanism: The `receive` function is not protected against reentrancy attacks, allowing an attacker to drain the contract's funds.
- Impact: An attacker can drain the funds of the `EvilCallback` contract by repeatedly calling the `receive` function and causing the contract to transfer more funds than intended.

# Unprotected Function in EvilToken
### <Unprotected Function>
- Location: `chain/ethereum/contracts/EvilToken.sol` : `transferFrom` function
- Mechanism: The `transferFrom` function is not protected against reentrancy attacks, allowing an attacker to drain the contract's funds.
- Impact: An attacker can drain the funds of the `EvilToken` contract by repeatedly calling the `transferFrom` function and causing the contract to transfer more funds than intended.

# Unprotected Function in StealToken
### <Unprotected Function>
- Location: `chain/ethereum/contracts/StealToken.sol` : `transfer` function
- Mechanism: The `transfer` function is not protected against reentrancy attacks, allowing an attacker to drain the contract's funds.
- Impact: An attacker can drain the funds of the `StealToken` contract by repeatedly calling the `transfer` function and causing the contract to transfer more funds than intended.

# Unprotected Function in THORChain_Aggregator
### <Unprotected Function>
- Location: `chain/ethereum/contracts/THORChain_Aggregator.sol` : `swapIn` function
- Mechanism: The `swapIn` function is not protected against reentrancy attacks, allowing an attacker to drain the contract's funds.
- Impact: An attacker can drain the funds of the `THORChain_Aggregator` contract by repeatedly calling the `swapIn` function and causing the contract to transfer more funds than intended.

# Unprotected Function in THORChain_Router
### <Unprotected Function>
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `transferOut` and `transferOutAndCall` functions
- Mechanism: The `transferOut` and `transferOutAndCall` functions are not protected against reentrancy attacks, allowing an attacker to drain the contract's funds.
- Impact: An attacker can drain the funds of the `THORChain_Router` contract by repeatedly calling the `transferOut` or `transferOutAndCall` functions and causing the contract to transfer more funds than intended.
