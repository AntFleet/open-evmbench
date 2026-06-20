# Audit: 2024-03-coinbase

## Reentrancy Vulnerability in `MagicSpend` Contract
- Location: `MagicSpend.sol` : `postOp()`
- Mechanism: The `postOp()` function is vulnerable to reentrancy attacks because it calls the `SafeTransferLib.forceSafeTransferETH()` function, which can lead to reentrancy if the recipient contract has a fallback function that calls back into the `MagicSpend` contract.
- Impact: An attacker can exploit this vulnerability by creating a contract that has a fallback function which calls the `MagicSpend` contract's `postOp()` function, causing it to transfer more Ether to the attacker's contract.

## Unprotected Function in `CoinbaseSmartWallet` Contract
- Location: `CoinbaseSmartWallet.sol` : `executeWithoutChainIdValidation()`
- Mechanism: The `executeWithoutChainIdValidation()` function does not check if the caller is an owner or the EntryPoint, allowing anyone to call this function and execute arbitrary code on behalf of the contract.
- Impact: An attacker can exploit this vulnerability by calling the `executeWithoutChainIdValidation()` function and executing malicious code on behalf of the contract.

## Use of Predictable Salt in `CoinbaseSmartWalletFactory` Contract
- Location: `CoinbaseSmartWalletFactory.sol` : `_getSalt()`
- Mechanism: The `_getSalt()` function uses a predictable salt value, which can be guessed by an attacker.
- Impact: An attacker can exploit this vulnerability by guessing the salt value and deploying a contract at the same address as the intended contract, potentially leading to unauthorized access or control.

## Unsecured Use of `transfer` in `WebAuthn` Library
- Location: `WebAuthn.sol` : `verify()`
- Mechanism: The `verify()` function uses the `transfer` function to send Ether, which can lead to issues if the recipient contract has a fallback function that reverts or runs out of gas.
- Impact: An attacker can exploit this vulnerability by creating a contract that has a fallback function which reverts or runs out of gas, preventing the Ether from being transferred and potentially disrupting the functionality of the `WebAuthn` library.

## Missing Input Validation in `MultiOwnable` Contract
- Location: `MultiOwnable.sol` : `_addOwnerAtIndex()`
- Mechanism: The `_addOwnerAtIndex()` function does not validate the input `owner` value, which can lead to issues if an invalid or malicious owner value is provided.
- Impact: An attacker can exploit this vulnerability by providing an invalid or malicious owner value, potentially leading to unauthorized access or control.

## Insecure Use of `ecdsa_verify` in `FCL` Library
- Location: `FCL.sol` : `ecdsa_verify()`
- Mechanism: The `ecdsa_verify()` function uses a potentially insecure implementation of the ECDSA verification algorithm, which can be vulnerable to certain attacks.
- Impact: An attacker can exploit this vulnerability by using a specially crafted signature that can bypass the verification check, potentially leading to unauthorized access or control.
