# Audit: 2024-05-loop

### Reentrancy Vulnerability
- Location: `src/PrelaunchPoints.sol` : `_fillQuote`
- Mechanism: The `_fillQuote` function calls an external contract (`exchangeProxy`) using the `call` method, which can potentially lead to reentrancy if the `exchangeProxy` contract is maliciously designed to reenter this contract. This could allow an attacker to drain the contract's funds or manipulate the `boughtETHAmount` calculation.
- Impact: An attacker could exploit this vulnerability to steal funds or manipulate the contract's state.

### Unprotected Function
- Location: `src/PrelaunchPoints.sol` : `receive`
- Mechanism: The `receive` function is not protected and allows anyone to send ETH to the contract, which could lead to unintended behavior or reentrancy attacks.
- Impact: An attacker could exploit this vulnerability to lock Ether in the contract forever or perform reentrancy attacks.

### Unvalidated Input
- Location: `src/PrelaunchPoints.sol` : `_decodeUniswapV3Data` and `_decodeTransformERC20Data`
- Mechanism: The input data from the 0x API is not thoroughly validated, which could lead to incorrect decoding or reentrancy vulnerabilities.
- Impact: An attacker could exploit this vulnerability to manipulate the decoding process or perform reentrancy attacks.

### Missing Access Control
- Location: `src/PrelaunchPoints.sol` : `convertAllETH`
- Mechanism: The `convertAllETH` function does not check if the Loop contract address has been set, which could allow an unauthorized user to convert all the locked ETH to lpETH.
- Impact: An attacker could exploit this vulnerability to convert all the locked ETH to lpETH without authorization.

### Use of `transfer` Instead of `safeTransfer`
- Location: `src/PrelaunchPoints.sol` : `recoverERC20`
- Mechanism: The `recoverERC20` function uses `transfer` instead of `safeTransfer` to transfer ERC20 tokens, which could lead to issues if the recipient contract does not support ERC20 tokens.
- Impact: An attacker could exploit this vulnerability to lock tokens in the contract.

### Unhandled Exception in `call`
- Location: `src/PrelaunchPoints.sol` : `_fillQuote`
- Mechanism: The `_fillQuote` function does not handle exceptions that may occur when calling the `exchangeProxy` contract using the `call` method.
- Impact: An attacker could exploit this vulnerability to cause the contract to revert and potentially lock funds.

### Missing Reentrancy Protection in `withdraw`
- Location: `src/PrelaunchPoints.sol` : `withdraw`
- Mechanism: The `withdraw` function does not protect against reentrancy attacks, which could allow an attacker to drain the contract's funds.
- Impact: An attacker could exploit this vulnerability to steal funds from the contract.

### Use of `uint32` for Timestamps
- Location: `src/PrelaunchPoints.sol` : `loopActivation`, `startClaimDate`
- Mechanism: The use of `uint32` for timestamps could lead to overflow issues in the future, potentially causing unintended behavior.
- Impact: An attacker could exploit this vulnerability to manipulate the contract's state or cause unintended behavior.

### Missing Input Validation in `lock` and `lockFor`
- Location: `src/PrelaunchPoints.sol` : `lock` and `lockFor`
- Mechanism: The `lock` and `lockFor` functions do not validate the input `_amount` parameter, which could lead to unintended behavior or reentrancy vulnerabilities.
- Impact: An attacker could exploit this vulnerability to manipulate the contract's state or perform reentrancy attacks.

### Missing Access Control in `allowToken`
- Location: `src/PrelaunchPoints.sol` : `allowToken`
- Mechanism: The `allowToken` function does not check if the token is already allowed, which could lead to unintended behavior or security vulnerabilities.
- Impact: An attacker could exploit this vulnerability to manipulate the contract's state or perform unauthorized actions.

### Use of `calldata` Instead of `memory`
- Location: `src/PrelaunchPoints.sol` : `_decodeUniswapV3Data` and `_decodeTransformERC20Data`
- Mechanism: The use of `calldata` instead of `memory` for the `_data` parameter could lead to issues with data decoding or reentrancy vulnerabilities.
- Impact: An attacker could exploit this vulnerability to manipulate the decoding process or perform reentrancy attacks.
