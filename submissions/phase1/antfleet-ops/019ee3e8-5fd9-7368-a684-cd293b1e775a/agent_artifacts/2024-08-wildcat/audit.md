# Audit: 2024-08-wildcat

## Unprotected Function in HooksFactory
- Location: src/HooksFactory.sol : `deployMarket` function
- Mechanism: The `deployMarket` function does not check if the `hooksData` bytes are 0 or greater than 32 bytes, potentially allowing incorrect or malicious data to be passed to `hooks.onCreateMarket`.
- Impact: An attacker could potentially manipulate the `hooksData` to execute unintended actions on the market through the `onCreateMarket` hook.


## Unprotected Function in HooksFactory
- Location: src/HooksFactory.sol : `deployMarketAndHooks` function
- Mechanism: The `deployMarketAndHooks` function does not check if the `hooksTemplateArgs` bytes are 0 or greater than 32 bytes, potentially allowing incorrect or malicious data to be passed to `hooks.onCreateMarket`.
- Impact: An attacker could potentially manipulate the `hooksTemplateArgs` to execute unintended actions on the market through the `onCreateMarket` hook.


## Unprotected Function in HooksFactory
- Location: src/HooksFactory.sol : `deployHooksInstance` function
- Mechanism: The `deployHooksInstance` function does not check if the `constructorArgs` bytes are 0 or greater than 32 bytes, potentially allowing incorrect or malicious data to be passed to the constructor of the hook.
- Impact: An attacker could potentially manipulate the `constructorArgs` to execute unintended actions on the hook.


## Unprotected Function in MarketConstraintHooks
- Location: src/access/MarketConstraintHooks.sol : `_readAddress` function
- Mechanism: The `_readAddress` function uses a hardcoded offset for the address without checking the length of the calldata, potentially allowing incorrect or malicious data to be passed to `validateCredential`.
- Impact: An attacker could potentially manipulate the calldata to execute unintended actions on the hook through the `validateCredential` function.


## Unprotected Function in AccessControlHooks
- Location: src/access/AccessControlHooks.sol : `_handleHooksData` function
- Mechanism: The `_handleHooksData` function uses a hardcoded offset for the address and credential data without checking the length of the calldata, potentially allowing incorrect or malicious data to be passed to `getCredential` or `validateCredential`.
- Impact: An attacker could potentially manipulate the calldata to execute unintended actions on the hook through the `getCredential` or `validateCredential` functions.


## Unprotected Function in AccessControlHooks
- Location: src/access/AccessControlHooks.sol : `onTransfer` function
- Mechanism: The `onTransfer` function does not check if the recipient is sanctioned before allowing the transfer, potentially allowing sanctioned entities to interact with the market.
- Impact: A sanctioned entity could potentially interact with the market by initiating a transfer.


## Reentrancy in HooksFactory
- Location: src/HooksFactory.sol : `addHooksTemplate` function
- Mechanism: If `addHooksTemplate` is called while `HooksTemplate` is being updated, it can lead to a reentrancy attack.
- Impact: An attacker could potentially manipulate the `HooksTemplate` to execute unintended actions.


## Reentrancy in FixedTermLoanHooks
- Location: src/access/FixedTermLoanHooks.sol : `addRoleProvider` function
- Mechanism: If `addRoleProvider` is called while `RoleProvider` is being updated, it can lead to a reentrancy attack.
- Impact: An attacker could potentially manipulate the `RoleProvider` to execute unintended actions.


## Missing Oracle Check in FixedTermLoanHooks
- Location: src/access/FixedTermLoanHooks.sol : `_tryGetCredential` function
- Mechanism: The `_tryGetCredential` function does not check the return value of `call` to ensure it returns a valid value.
- Impact: If the `call` to `getCredential` reverts or does not return a valid value, the function will not handle it correctly.


## Missing Oracle Check in FixedTermLoanHooks
- Location: src/access/FixedTermLoanHooks.sol : `_tryValidateCredential` function
- Mechanism: The `_tryValidateCredential` function does not check the return value of `call` to ensure it returns a valid value.
- Impact: If the `call` to `validateCredential` reverts or does not return a valid value, the function will not handle it correctly.


## Missing Oracle Check in FixedTermLoanHooks
- Location: src/access/FixedTermLoanHooks.sol : `onExecuteWithdrawal` function
- Mechanism: The `onExecuteWithdrawal` function does not check if the `hooksData` bytes are 0 or greater than 32 bytes, potentially allowing incorrect or malicious data to be passed to `hooks.onExecuteWithdrawal`.
- Impact: An attacker could potentially manipulate the `hooksData` to execute unintended actions on the market through the `onExecuteWithdrawal` hook.


## Empty Calldata in AccessControlHooks
- Location: src/access/AccessControlHooks.sol : `onDeposit` function
- Mechanism: The `onDeposit` function does not check if the `hooksData` is empty, potentially allowing unintended actions.
- Impact: An attacker could potentially manipulate the `hooksData` to execute unintended actions on the hook through the `onQueueWithdrawal` function.


## Empty Calldata in FixedTermLoanHooks
- Location: src/access/FixedTermLoanHooks.sol : `onDeposit` function
- Mechanism: The `onDeposit` function does not check if the `hooksData` is empty, potentially allowing unintended actions.
- Impact: An attacker could potentially manipulate the `hooksData` to execute unintended actions on the hook through the `onQueueWithdrawal` function.


## Missing input validation for `feeRecipient` and `originationFeeAsset`
- Location: src/HooksFactory.sol : `addHooksTemplate` function
- Mechanism: The `addHooksTemplate` function does not validate the `feeRecipient` and `originationFeeAsset` inputs.
- Impact: This could potentially lead to incorrect or malicious market templates being added.


## Unchecked Users in AccessControlHooks
- Location: src/access/AccessControlHooks.sol : `onTransfer` function
- Mechanism: The `onTransfer` function does not check if the recipient is an approved user before allowing the transfer.
- Impact: A non-approved user could potentially interact with the market.


## Missing Oracle Check in HooksFactory
- Location: src/HooksFactory.sol : `deployMarket` function
- Mechanism: The `deployMarket` function does not check the return value of `call` to ensure it returns a valid value.
- Impact: If the `call` to `onCreateMarket` reverts or does not return a valid value, the function will not handle it correctly.


## Missing Oracle Check in AccessControlHooks
- Location: src/access/AccessControlHooks.sol : `onQueueWithdrawal` function
- Mechanism: The `onQueueWithdrawal` function does not check the return value of `call` to ensure it returns a valid value.
- Impact: If the `call` to `hooks.onQueueWithdrawal` reverts or does not return a valid value, the function will not handle it correctly.


## Missing Oracle Check in FixedTermLoanHooks
- Location: src/access/FixedTermLoanHooks.sol : `onQueueWithdrawal` function
- Mechanism: The `onQueueWithdrawal` function does not check the return value of `call` to ensure it returns a valid value.
- Impact: If the `call` to `hooks.onQueueWithdrawal` reverts or does not return a valid value, the function will not handle it correctly.


## Incorrect Use of Mapping in WildcatArchController
- Location: src/WildcatArchController.sol : `registerControllerFactory` function
- Mechanism: The `registerControllerFactory` function uses a mapping to store and retrieve factory addresses, but it does not check for duplicates.
- Impact: If a factory address is registered multiple times, it will cause unexpected behavior.


## Incorrect Use of Mapping in WildcatArchController
- Location: src/WildcatArchController.sol : `removeControllerFactory` function
- Mechanism: The `removeControllerFactory` function uses a mapping to store and retrieve factory addresses, but it does not check if the address exists before removing it.
- Impact: If the address does not exist, it will cause unexpected behavior.


## Incorrect Use of Mapping in WildcatArchController
- Location: src/WildcatArchController.sol : `registerController` function
- Mechanism: The `registerController` function uses a mapping to store and retrieve controller addresses, but it does not check for duplicates.
- Impact: If a controller address is registered multiple times, it will cause unexpected behavior.


## Incorrect Use of Mapping in WildcatArchController
- Location: src/WildcatArchController.sol : `removeController` function
- Mechanism: The `removeController` function uses a mapping to store and retrieve controller addresses, but it does not check if the address exists before removing it.
- Impact: If the address does not exist, it will cause unexpected behavior.


## Incorrect Use of Mapping in WildcatArchController
- Location: src/WildcatArchController.sol : `registerBorrower` function
- Mechanism: The `registerBorrower` function uses a mapping to store and retrieve borrower addresses, but it does not check for duplicates.
- Impact: If a borrower address is registered multiple times, it will cause unexpected behavior.


## Incorrect Use of Mapping in WildcatArchController
- Location: src/WildcatArchController.sol : `removeBorrower` function
- Mechanism: The `removeBorrower` function uses a mapping to store and retrieve borrower addresses, but it does not check if the address exists before removing it.
- Impact: If the address does not exist, it will cause unexpected behavior.


## Unchecked Asset in WildcatArchController
- Location: src/WildcatArchController.sol : `addBlacklist` function
- Mechanism: The `addBlacklist` function does not check if the asset is valid before adding it to the blacklist.
- Impact: An attacker could potentially add an invalid asset to the blacklist.


## Unchecked Asset in WildcatArchController
- Location: src/WildcatArchController.sol : `removeBlacklist` function
- Mechanism: The `removeBlacklist` function does not check if the asset is valid before removing it from the blacklist.
- Impact: An attacker could potentially remove an invalid asset from the blacklist.


## Incorrect Reentrancy Protection in AccessControlHooks
- Location: src/access/AccessControlHooks.sol : `onQueueWithdrawal` function
- Mechanism: The `onQueueWithdrawal` function uses a non-reentrancy modifier, but it does not check for reentrancy attacks.
- Impact: An attacker could potentially execute a reentrancy attack on the `onQueueWithdrawal` function.


## Incorrect Reentrancy Protection in FixedTermLoanHooks
- Location: src/access/FixedTermLoanHooks.sol : `onQueueWithdrawal` function
- Mechanism: The `onQueueWithdrawal` function uses a non-reentrancy modifier, but it does not check for reentrancy attacks.
- Impact: An attacker could potentially execute a reentrancy attack on the `onQueueWithdrawal` function.


## Unprotected Function in WildcatMarket
- Location: src/market/WildcatMarket.sol : `deposit` function
- Mechanism: The `deposit` function does not check if the deposit amount is greater than the available liquidity, potentially allowing an attacker to execute unintended actions.
- Impact: An attacker could potentially execute unintended actions on the market by depositing more than the available liquidity.


## Unprotected Function in WildcatMarket
- Location: src/market/WildcatMarket.sol : `borrow` function
- Mechanism: The `borrow` function does not check if the borrower has sufficient assets to cover the loan, potentially allowing an attacker to execute unintended actions.
- Impact: An attacker could potentially execute unintended actions on the market by borrowing more than the available assets.


## Missing Oracle Check in WildcatMarket
- Location: src/market/WildcatMarket.sol : `closeMarket` function
- Mechanism: The `closeMarket` function does not check the return value of `call` to ensure it returns a valid value.
- Impact: If the `call` to `hooks.onCloseMarket` reverts or does not return a valid value, the function will not handle it correctly.


## Missing Oracle Check in WildcatMarket
- Location: src/market/WildcatMarket.sol : `repayAndProcessUnpaidWithdrawalBatches` function
- Mechanism: The `repayAndProcessUnpaidWithdrawalBatches` function does not check the return value of `call` to ensure it returns a valid value.
- Impact: If the `call` to `hooks.onRepay` reverts or does not return a valid value, the function will not handle it correctly.


## Incorrect Use of Mapping in WildcatMarket
- Location: src/market/WildcatMarket.sol : `get HooksTemplateDetails` function
- Mechanism: The `get HooksTemplateDetails` function uses a mapping to store and retrieve HooksTemplate details, but it does not check for duplicates.
- Impact: If a HooksTemplate detail is registered multiple times, it will cause unexpected behavior.


## Unchecked Users in WildcatMarket
- Location: src/market/WildcatMarket.sol : `onTransfer` function
- Mechanism: The `onTransfer` function does not check if the recipient is an approved user before allowing the transfer.
- Impact: A non-approved user could potentially interact with the market.


## Unchecked Asset in WildcatMarket
- Location: src/market/WildcatMarket.sol : `deposit` function
- Mechanism: The `deposit` function does not check if the asset is valid before depositing it.
- Impact: An attacker could potentially deposit an invalid asset.


## Unchecked Asset in WildcatMarket
- Location: src/market/WildcatMarket.sol : `borrow` function
- Mechanism: The `borrow` function does not check if the asset is valid before borrowing it.
- Impact: An attacker could potentially borrow an invalid asset.


## Unchecked Asset in WildcatMarket
- Location: src/market/WildcatMarket.sol : `closeMarket` function
- Mechanism: The `closeMarket` function does not check if the asset is valid before closing the market.
- Impact: An attacker could potentially close the market with an invalid asset.


## Missing Oracle Check in WildcatMarketWithdrawals
- Location: src/market/WildcatMarketWithdrawals.sol : `executeWithdrawal` function
- Mechanism: The `executeWithdrawal` function does not check the return value of `call` to ensure it returns a valid value.
- Impact: If the `call` to `hooks.onExecuteWithdrawal` reverts or does not return a valid value, the function will not handle it correctly.


## Incorrect Use of Mapping in WildcatMarketWithdrawals
- Location: src/market/WildcatMarketWithdrawals.sol : `getWithdrawalBatch` function
- Mechanism: The `getWithdrawalBatch` function uses a mapping to store and retrieve withdrawal batch details, but it does not check for duplicates.
- Impact: If a withdrawal batch detail is registered multiple times, it will cause unexpected behavior.


## Unchecked Users in WildcatMarketWithdrawals
- Location: src/market/WildcatMarketWithdrawals.sol : `executeWithdrawal` function
- Mechanism: The `executeWithdrawal` function does not check if the user is an approved user before allowing the withdrawal.
- Impact: A non-approved user could potentially interact with the market.


## Unchecked Asset in WildcatMarketWithdrawals
- Location: src/market/WildcatMarketWithdrawals.sol : `executeWithdrawal` function
- Mechanism: The `executeWithdrawal` function does not check if the asset is valid before executing the withdrawal.
- Impact: An attacker could potentially execute a withdrawal with an invalid asset.


## Missing Input Validation in WildcatMarketConfig
- Location: src/market/WildcatMarketConfig.sol : `onSetMaxTotalSupply` function
- Mechanism: The `onSetMaxTotalSupply` function does not validate the `maxTotalSupply` input.
- Impact: An attacker could potentially set an invalid `maxTotalSupply` value.


## Missing Input Validation in WildcatMarketConfig
- Location: src/market/WildcatMarketConfig.sol : `setAnnualInterestAndReserveRatioBips` function
- Mechanism: The `setAnnualInterestAndReserveRatioBips` function does not validate the `annualInterestBips` and `reserveRatioBips` inputs.
- Impact: An attacker could potentially set invalid `annualInterestBips` and `reserveRatioBips` values.


## Missing Input Validation in WildcatMarketToken
- Location: src/market/WildcatMarketToken.sol : `approve` function
- Mechanism: The `approve` function does not validate the `spender` and `amount` inputs.
- Impact: An attacker could potentially approve an invalid `spender` or `amount` value.


## Missing Input Validation in WildcatMarketToken
- Location: src/market/WildcatMarketToken.sol : `transferFrom` function
- Mechanism: The `transferFrom` function does not validate the `from`, `to`, and `amount` inputs.
- Impact: An attacker could potentially transfer an invalid `from`, `to`, or `amount` value.


## Missing Input Validation in WildcatMarketToken
- Location: src/market/WildcatMarketToken.sol : `transfer` function
- Mechanism: The `transfer` function does not validate the `to` and `amount` inputs.
- Impact: An attacker could potentially transfer an invalid `to` or `amount` value.


## Unchecked Asset in WildcatMarketToken
- Location: src/market/WildcatMarketToken.sol : `transfer` function
- Mechanism: The `transfer` function does not check if the asset is valid before transferring it.
- Impact: An attacker could potentially transfer an invalid asset.


## Unchecked Asset in WildcatMarketToken
- Location: src/market/WildcatMarketToken.sol : `transferFrom` function
- Mechanism: The `transferFrom` function does not check if the asset is valid before transferring it.
- Impact: An attacker could potentially transfer an invalid asset.


## Missing Oracle Check in WildcatMarketToken
- Location: src/market/WildcatMarketToken.sol : `onTransfer` function
- Mechanism: The `onTransfer` function does not check the return value of `call` to ensure it returns a valid value.
- Impact: If the `call` to `hooks.onTransfer` reverts or does not return a valid value, the function will not handle it correctly.


## Unprotected Function in WildcatMarketToken
- Location: src/market/WildcatMarketToken.sol : `transfer` function
- Mechanism: The `transfer` function does not check if the `to` address is valid before transferring the tokens.
- Impact: An attacker could potentially transfer tokens to an invalid address.


## Unprotected Function in WildcatMarketToken
- Location: src/market/WildcatMarketToken.sol : `transferFrom` function
- Mechanism: The `transferFrom` function does not check if the `from` address is valid before transferring the tokens.
- Impact: An attacker could potentially transfer tokens from an invalid address.


## Unchecked User in WildcatMarketToken
- Location: src/market/WildcatMarketToken.sol : `transfer` function
- Mechanism: The `transfer` function does not check if the user is an approved user before allowing the transfer.
- Impact: A non-approved user could potentially interact with the market.


## Unchecked Asset in WildcatMarketToken
- Location: src/market/WildcatMarketToken.sol : `approve` function
- Mechanism: The `approve` function does not check if the asset is valid before approving it.
- Impact: An attacker could potentially approve an invalid asset.


## Unchecked Asset in WildcatMarketToken
- Location: src/market/WildcatMarketToken.sol : `transferFrom` function
- Mechanism: The `transferFrom` function does not check if the asset is valid before transferring it.
- Impact: An attacker could potentially transfer an invalid asset.


## Unchecked Asset in WildcatMarketToken
- Location: src/market/WildcatMarketToken.sol : `transfer` function
- Mechanism: The `transfer` function does not check if the asset is valid before transferring it.
- Impact: An attacker could potentially transfer an invalid asset.


## Reentrancy Vulnerability in HooksFactory
- Location: src/HooksFactory.sol : `pushProtocolFeeBipsUpdates` function
- Mechanism: Reentrancy attacks can occur because no reentrancy protection is used in this function.
- Impact: An attacker could potentially drain the funds of the contract by using a reentrancy attack.


## Reentrancy Vulnerability in AccessControlHooks
- Location: src/access/AccessControlHooks.sol : `onQueueWithdrawal` function
- Mechanism: Reentrancy attacks can occur because no reentrancy protection is used in this function.
- Impact: An attacker could potentially drain the funds of the contract by using a reentrancy attack.


## Reentrancy Vulnerability in FixedTermLoanHooks
- Location: src/access/FixedTermLoanHooks.sol : `onQueueWithdrawal` function
- Mechanism: Reentrancy attacks can occur because no reentrancy protection is used in this function.
- Impact: An attacker could potentially drain the funds of the contract by using a reentrancy attack.


## Unprotected Function in WildcatMarketWithdrawals
- Location: src/market/WildcatMarketWithdrawals.sol : `executeWithdrawal` function
- Mechanism: The `executeWithdrawal` function does not check if the `accountAddress` is valid before executing the withdrawal.
- Impact: An attacker could potentially execute a withdrawal for an invalid account.


## Missing Oracle Check in WildcatMarketWithdrawals
- Location: src/market/WildcatMarketWithdrawals.sol : `executeWithdrawal` function
- Mechanism: The `executeWithdrawal` function does not check the return value of `call` to ensure it returns a valid value.
- Impact: If the `call` to `hooks.onExecuteWithdrawal` reverts or does not return a valid value, the function will not handle it correctly.


## Unchecked User in WildcatMarketWithdrawals
- Location: src/market/WildcatMarketWithdrawals.sol : `executeWithdrawal` function
- Mechanism: The `executeWithdrawal` function does not check if the user is an approved user before allowing the withdrawal.
- Impact: A non-approved user could potentially interact with the market.


## Missing Input Validation in WildcatMarketWithdrawals
- Location: src/market/WildcatMarketWithdrawals.sol : `executeWithdrawals` function
- Mechanism: The `executeWithdrawals` function does not validate the `accountAddresses` and `expiries` inputs.
- Impact: An attacker could potentially execute a withdrawal with invalid `accountAddresses` or `expiries`.


## Incorrect Use of Mapping in WildcatMarketWithdrawals
- Location: src/market/WildcatMarketWithdrawals.sol : `getUnpaidBatchExpiries` function
- Mechanism: The `getUnpaidBatchExpiries` function uses a mapping to store and retrieve withdrawal batch expiries, but it does not check for duplicates.
- Impact: If a withdrawal batch expiry is registered multiple times, it will cause unexpected behavior.


## Unchecked Asset in WildcatMarketWithdrawals
- Location: src/market/WildcatMarketWithdrawals.sol : `executeWithdrawal` function
- Mechanism: The `executeWithdrawal` function does not check if the asset is valid before executing the withdrawal.
- Impact: An attacker could potentially execute a withdrawal with an invalid asset.


## Missing Input Validation in WildcatMarketWithdrawals
- Location: src/market/WildcatMarketWithdrawals.sol : `executeWithdrawals` function
- Mechanism: The `executeWithdrawals` function does not validate the `accountAddresses` and `expiries` inputs.
- Impact: An attacker could potentially execute withdrawals with invalid `accountAddresses` or `expiries`.
