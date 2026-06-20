# Audit: 2023-07-pooltogether

## Reentrancy Vulnerability in `_withdraw` Function
- Location: `Vault.sol` : `_withdraw` function
- Mechanism: The `_withdraw` function first burns the shares and then transfers the assets to the receiver. An attacker could exploit this by reentering the contract after the shares are burned but before the assets are transferred, allowing them to withdraw more assets than they are entitled to.
- Impact: An attacker could drain the contract of its assets by repeatedly reentering the `_withdraw` function.

## Unprotected Function
- Location: `VaultFactory.sol` : `deployVault` function
- Mechanism: The `deployVault` function does not have any access control, allowing anyone to deploy a new vault.
- Impact: An attacker could deploy a large number of vaults, potentially leading to a denial-of-service attack or other malicious behavior.

## Use of Tx-Origin
- Location: `Vault.sol` : various functions
- Mechanism: The contract uses `msg.sender` to authenticate users, but this can be spoofed using the `tx.origin` attack.
- Impact: An attacker could trick a user into calling a function on the contract, allowing the attacker to perform actions on behalf of the user.

## Lack of Input Validation
- Location: `Vault.sol` : various functions
- Mechanism: The contract does not validate all inputs to its functions, potentially allowing an attacker to pass in malicious data.
- Impact: An attacker could pass in malformed or malicious data, potentially crashing the contract or executing unintended behavior.

## Reentrancy Vulnerability in `_liquidate` Function
- Location: `Vault.sol` : `_liquidate` function
- Mechanism: The `_liquidate` function calls the `contributePrizeTokens` function on the `PrizePool` contract, which could potentially reenter the `Vault` contract.
- Impact: An attacker could exploit this reentrancy vulnerability to drain the contract of its assets or execute other malicious behavior.

## Unsecured Use of `transfer` and `transferFrom`
- Location: `Vault.sol` : various functions
- Mechanism: The contract uses `transfer` and `transferFrom` to move assets, but these functions can fail if the recipient contract does not support them.
- Impact: An attacker could potentially cause the contract to lose assets if the recipient contract does not support `transfer` or `transferFrom`.

## Missing Access Control
- Location: `Vault.sol` : `claimPrizes` function
- Mechanism: The `claimPrizes` function does not check if the caller is the claimer, allowing anyone to claim prizes.
- Impact: An attacker could claim prizes on behalf of other users, potentially stealing their winnings.

## Potential Division by Zero
- Location: `Vault.sol` : `_convertToShares` and `_convertToAssets` functions
- Mechanism: The contract divides by the `_assetUnit` variable, which could potentially be zero.
- Impact: If `_assetUnit` is zero, the contract will revert with a division by zero error, potentially causing unintended behavior.

## Use of Unsecured `approve` Function
- Location: `VaultFactory.sol` : `deployVault` function
- Mechanism: The contract uses the `approve` function to grant the `YieldVault` contract access to the `Vault` contract's assets, but this function can be used to grant unnecessary permissions.
- Impact: An attacker could potentially exploit the `approve` function to grant themselves or another contract access to the `Vault` contract's assets.
