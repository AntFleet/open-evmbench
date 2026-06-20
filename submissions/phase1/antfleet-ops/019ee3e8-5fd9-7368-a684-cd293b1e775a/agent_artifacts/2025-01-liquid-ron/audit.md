# Audit: 2025-01-liquid-ron

### Reentrancy Vulnerability in `Escrow` Contract
- Location: `Escrow.sol` : `deposit` function
- Mechanism: The `deposit` function in the `Escrow` contract calls the `deposit` function of the `IVault` contract, passing the `_amount` and `_receiver` as arguments. However, the `_receiver` is not validated to ensure it's not a contract that can re-enter this function, potentially leading to reentrancy attacks.
- Impact: An attacker could potentially drain the contract's funds by re-entering the `deposit` function and manipulating the state of the contract.

### Unprotected Function in `LiquidProxy` Contract
- Location: `LiquidProxy.sol` : `receive` function
- Mechanism: The `receive` function in the `LiquidProxy` contract remains open, allowing any contract to send funds to it without restrictions. This can potentially lead to unintended behavior or attacks if not properly validated.
- Impact: An attacker could exploit this function to send malicious transactions or manipulate the contract's state.

### Unvalidated Input in `LiquidRon` Contract
- Location: `LiquidRon.sol` : `deployStakingProxy` function
- Mechanism: The `deployStakingProxy` function in the `LiquidRon` contract deploys a new `LiquidProxy` contract without validating the input parameters. This can potentially lead to incorrect or malicious contract deployments.
- Impact: An attacker could exploit this function to deploy malicious contracts or manipulate the state of the `LiquidRon` contract.

### Potential Front-Running Attack in `LiquidRon` Contract
- Location: `LiquidRon.sol` : `harvestAndDelegateRewards` function
- Mechanism: The `harvestAndDelegateRewards` function in the `LiquidRon` contract calls the `harvestAndDelegateRewards` function of the `ILiquidProxy` contract, passing the `_consensusAddrs` and `_consensusAddrDst` as arguments. However, this function is not protected against front-running attacks, where an attacker can manipulate the transaction order to steal rewards.
- Impact: An attacker could potentially steal rewards by front-running the `harvestAndDelegateRewards` function.

### Use of `transfer` Instead of `SafeERC20.safeTransfer` in `RonHelper` Contract
- Location: `RonHelper.sol` : `_withdrawRONTo` function
- Mechanism: The `_withdrawRONTo` function in the `RonHelper` contract uses the `transfer` function instead of `SafeERC20.safeTransfer` to transfer tokens. This can potentially lead to issues with token transfers, especially if the recipient contract has a complex token reception logic.
- Impact: An attacker could exploit this function to manipulate the token transfer logic or steal tokens.

### Lack of Input Validation in `ValidatorTracker` Contract
- Location: `ValidatorTracker.sol` : `_tryPushValidator` function
- Mechanism: The `_tryPushValidator` function in the `ValidatorTracker` contract pushes a new validator to the list without validating the input. This can potentially lead to incorrect or malicious validator additions.
- Impact: An attacker could exploit this function to add malicious validators to the list, potentially manipulating the state of the contract.

### Potential Reentrancy Vulnerability in `Pausable` Contract
- Location: `Pausable.sol` : `pause` and `unpause` functions
- Mechanism: The `pause` and `unpause` functions in the `Pausable` contract do not have reentrancy protection. This can potentially lead to reentrancy attacks if an attacker can manipulate the contract's state during the pause or unpause process.
- Impact: An attacker could potentially exploit this vulnerability to drain the contract's funds or manipulate its state.
