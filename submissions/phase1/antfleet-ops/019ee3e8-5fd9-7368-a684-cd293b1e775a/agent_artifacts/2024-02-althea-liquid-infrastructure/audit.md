# Audit: 2024-02-althea-liquid-infrastructure

## Reentrancy Vulnerability in `distribute` Function
- Location: `liquid-infrastructure/contracts/LiquidInfrastructureERC20.sol` : `distribute` function
- Mechanism: The `distribute` function calls `IERC20(toDistribute).transfer(recipient, entitlement)` in a loop, which can lead to reentrancy attacks if any of the `toDistribute` ERC20 contracts have a fallback function that calls back into this contract.
- Impact: An attacker could drain the funds of this contract by exploiting the reentrancy vulnerability, potentially leading to financial loss.

## Unprotected Function in `withdrawBalancesTo`
- Location: `liquid-infrastructure/contracts/LiquidInfrastructureNFT.sol` : `withdrawBalancesTo` function
- Mechanism: The `withdrawBalancesTo` function does not have any access control modifiers, allowing anyone to call it and potentially drain the contract's funds.
- Impact: An attacker could call `withdrawBalancesTo` to transfer the contract's funds to their own account, leading to financial loss.

## Missing Input Validation in `setThresholds`
- Location: `liquid-infrastructure/contracts/LiquidInfrastructureNFT.sol` : `setThresholds` function
- Mechanism: The `setThresholds` function does not validate if the input `newErc20s` and `newAmounts` arrays have the same length, which could lead to incorrect threshold values being set.
- Impact: An attacker could exploit this lack of validation to set incorrect threshold values, potentially disrupting the functionality of the contract.

## Unrestricted Access in `addManagedNFT`
- Location: `liquid-infrastructure/contracts/LiquidInfrastructureERC20.sol` : `addManagedNFT` function
- Mechanism: The `addManagedNFT` function does not restrict access to the owner, allowing anyone to call it and potentially add malicious NFT contracts to the `ManagedNFTs` array.
- Impact: An attacker could call `addManagedNFT` to add malicious NFT contracts, potentially leading to financial loss or disruption of the contract's functionality.

## Missing Reentrancy Protection in `mintAndDistribute`
- Location: `liquid-infrastructure/contracts/LiquidInfrastructureERC20.sol` : `mintAndDistribute` function
- Mechanism: The `mintAndDistribute` function calls `distributeToAllHolders` and then `mint`, which can lead to reentrancy attacks if an attacker can manipulate the `distributeToAllHolders` function to call back into this contract.
- Impact: An attacker could exploit this lack of reentrancy protection to drain the contract's funds or disrupt its functionality.

## Potential Denial-of-Service (DoS) in `distributeToAllHolders`
- Location: `liquid-infrastructure/contracts/LiquidInfrastructureERC20.sol` : `distributeToAllHolders` function
- Mechanism: The `distributeToAllHolders` function calls `distribute` in a loop, which can lead to a Denial-of-Service (DoS) attack if the number of holders is very large, causing the transaction to exceed the block gas limit.
- Impact: An attacker could exploit this DoS vulnerability to prevent the contract from functioning correctly, potentially leading to financial loss or disruption of the contract's functionality.
