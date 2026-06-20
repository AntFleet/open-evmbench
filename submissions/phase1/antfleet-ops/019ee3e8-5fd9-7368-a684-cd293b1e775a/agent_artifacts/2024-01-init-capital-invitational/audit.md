# Audit: 2024-01-init-capital-invitational

## 1. Reentrancy Vulnerability
- **Location**: `contracts/core/InitCore.sol` : `multicall` function
- **Mechanism**: The `multicall` function is vulnerable to reentrancy attacks. An attacker can manipulate the `results` array to reenter the contract and drain its funds.
- **Impact**: An attacker can drain the contract's funds by reentering the contract and executing arbitrary code.

## 2. Unprotected Function
- **Location**: `contracts/core/InitCore.sol` : `callback` function
- **Mechanism**: The `callback` function is not protected against unauthorized access. An attacker can call this function and execute arbitrary code on the contract.
- **Impact**: An attacker can execute arbitrary code on the contract and potentially drain its funds.

## 3. Unvalidated Input
- **Location**: `contracts/core/InitCore.sol` : `setConfig` function
- **Mechanism**: The `setConfig` function does not validate the input `_config` address. An attacker can set the config address to a malicious contract and potentially drain the contract's funds.
- **Impact**: An attacker can set the config address to a malicious contract and potentially drain the contract's funds.

## 4. Unprotected Function
- **Location**: `contracts/core/InitCore.sol` : `setOracle` function
- **Mechanism**: The `setOracle` function is not protected against unauthorized access. An attacker can call this function and set the oracle address to a malicious contract.
- **Impact**: An attacker can set the oracle address to a malicious contract and potentially manipulate the contract's behavior.

## 5. Unvalidated Input
- **Location**: `contracts/core/InitCore.sol` : `setLiqIncentiveCalculator` function
- **Mechanism**: The `setLiqIncentiveCalculator` function does not validate the input `_liqIncentiveCalculator` address. An attacker can set the liqIncentiveCalculator address to a malicious contract and potentially drain the contract's funds.
- **Impact**: An attacker can set the liqIncentiveCalculator address to a malicious contract and potentially drain the contract's funds.

## 6. Unprotected Function
- **Location**: `contracts/core/InitCore.sol` : `setRiskManager` function
- **Mechanism**: The `setRiskManager` function is not protected against unauthorized access. An attacker can call this function and set the riskManager address to a malicious contract.
- **Impact**: An attacker can set the riskManager address to a malicious contract and potentially manipulate the contract's behavior.

## 7. Reentrancy Vulnerability
- **Location**: `contracts/hook/MarginTradingHook.sol` : `coreCallback` function
- **Mechanism**: The `coreCallback` function is vulnerable to reentrancy attacks. An attacker can manipulate the `SwapInfo` struct to reenter the contract and drain its funds.
- **Impact**: An attacker can drain the contract's funds by reentering the contract and executing arbitrary code.

## 8. Unprotected Function
- **Location**: `contracts/hook/MarginTradingHook.sol` : `fillOrder` function
- **Mechanism**: The `fillOrder` function is not protected against unauthorized access. An attacker can call this function and execute arbitrary code on the contract.
- **Impact**: An attacker can execute arbitrary code on the contract and potentially drain its funds.

## 9. Unvalidated Input
- **Location**: `contracts/hook/MarginTradingHook.sol` : `addStopLossOrder` function
- **Mechanism**: The `addStopLossOrder` function does not validate the input `_triggerPrice_e36` and `_limitPrice_e36` values. An attacker can set these values to arbitrary numbers and potentially manipulate the contract's behavior.
- **Impact**: An attacker can set these values to arbitrary numbers and potentially manipulate the contract's behavior.

## 10. Unprotected Function
- **Location**: `contracts/hook/MarginTradingHook.sol` : `addTakeProfitOrder` function
- **Mechanism**: The `addTakeProfitOrder` function is not protected against unauthorized access. An attacker can call this function and execute arbitrary code on the contract.
- **Impact**: An attacker can execute arbitrary code on the contract and potentially drain its funds.
