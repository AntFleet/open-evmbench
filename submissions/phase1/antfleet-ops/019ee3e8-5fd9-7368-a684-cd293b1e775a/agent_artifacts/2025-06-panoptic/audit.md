# Audit: 2025-06-panoptic

## Reentrancy Vulnerability
- Location: `HypoVault.sol` : `executeWithdrawal` function
- Mechanism: The `executeWithdrawal` function first calculates the assets to be withdrawn and then calls `SafeTransferLib.safeTransfer` to transfer the assets to the user. However, before the transfer, it updates the `reservedWithdrawalAssets` variable. If an attacker is able to reenter this function before the transfer is executed, they can drain the contract's funds by repeatedly calling `executeWithdrawal`.
- Impact: An attacker can drain the contract's funds by repeatedly calling `executeWithdrawal` and reentering the function before the transfer is executed.

## Unprotected Function
- Location: `HypoVault.sol` : `manage` function
- Mechanism: The `manage` function allows the manager to make arbitrary function calls from the contract. However, it does not check if the target contract is a vault accountant contract or not. This allows an attacker to call any function on any contract, potentially leading to unauthorized actions.
- Impact: An attacker can use the `manage` function to call any function on any contract, potentially leading to unauthorized actions.

## Unvalidated Input
- Location: `PanopticVaultAccountant.sol` : `computeNAV` function
- Mechanism: The `computeNAV` function does not validate the `managerInput` parameter. If the input is malformed or contains incorrect data, the function may revert or produce incorrect results.
- Impact: An attacker can provide malformed or incorrect input to the `computeNAV` function, potentially causing it to revert or produce incorrect results.

## Unprotected State Variables
- Location: `HypoVault.sol` : `feeWallet`, `manager`, `accountant` variables
- Mechanism: The state variables `feeWallet`, `manager`, and `accountant` are not protected by any access control modifiers. This allows any user to modify these variables and potentially take control of the contract.
- Impact: An attacker can modify the `feeWallet`, `manager`, and `accountant` variables and potentially take control of the contract.

## Front-Running Vulnerability
- Location: `HypoVault.sol` : `fulfillDeposits` and `fulfillWithdrawals` functions
- Mechanism: The `fulfillDeposits` and `fulfillWithdrawals` functions do not have any protection against front-running attacks. An attacker can front-run these functions and potentially manipulate the contract's state.
- Impact: An attacker can front-run the `fulfillDeposits` and `fulfillWithdrawals` functions and potentially manipulate the contract's state.

## Reentrancy Vulnerability in `transfer` and `transferFrom` Functions
- Location: `HypoVault.sol` : `transfer` and `transferFrom` functions
- Mechanism: The `transfer` and `transferFrom` functions call the `_transferBasis` function, which updates the `userBasis` mapping. However, if an attacker is able to reenter these functions, they can potentially manipulate the `userBasis` mapping and drain the contract's funds.
- Impact: An attacker can reenter the `transfer` and `transferFrom` functions and potentially manipulate the `userBasis` mapping, draining the contract's funds.
