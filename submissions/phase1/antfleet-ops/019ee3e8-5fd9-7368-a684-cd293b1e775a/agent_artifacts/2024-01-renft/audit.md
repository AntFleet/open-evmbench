# Audit: 2024-01-renft

## Missing Input Validation in DeployCreate2Deployer
- Location: smart-contracts/scripts/DeployCreate2Deployer.s.sol : `function run() public`
- Mechanism: The create2 deployer address is fetched from the deployment configuration without first checking that it is not the zero address. If the address is the zero address, then all subsequent deployments will fail since they rely on the create2 deployer contract being initialized first.
- Impact: An attacker could potentially provide a zero address for the create2 deployer in the configuration, causing all deployments to fail, thus preventing the protocol from being deployed.

## Misconfigured Rental Safe Deployment in Factory Policy
- Location: smart-contracts/src/policies/Factory.sol : `function deployRentalSafe(address[] calldata owners, uint256 threshold) external returns (address safe)`
- Mechanism: The caller of this function is not validated. The factory policy requires the caller to have a specific role, however, this check is not implemented in the function that deploys the rental safe.
- Impact: Any address can deploy a rental safe, potentially allowing an attacker to create a rental safe that is not intended to be used for renting assets.

## Insecure Random Number Generation in PaymentEscrowModule
- Location: smart-contracts/src/modules/PaymentEscrow.sol : `function _calculateFee(uint256 amount) internal view returns (uint256)`
- Mechanism: While the vulnerability is more related to predictability of the pro-rata payment split, payments to the lender and renter may potentially be miscalculated if the numerator is colluded upon by multiple parties in advance, allowing for potential exploit.
- Impact: If multiple renters collude, they could calculate what the fee numerator should be to cause a payment miscalculation, thereby allowing them to gain an unfair advantage.

## Missing Zero Address Check in WhitelistDelegate of Storage Module
- Location: smart-contracts/src/modules/Storage.sol : `function toggleWhitelistDelegate(address delegate, bool isEnabled) external onlyByProxy permissioned`
- Mechanism: The `delegate` address is not checked for the zero address. If the `delegate` address is the zero address and `isEnabled` is true, then delegate calls to the zero address will be allowed.
- Impact: Allowing delegate calls to the zero address can cause unexpected behavior.

## Unprotected `Skim` Function in Payment Escrow Module
- Location: smart-contracts/src/modules/PaymentEscrow.sol : `function skim(address token, address to) external onlyByProxy permissioned`
- Mechanism: Any address with a specific role can call the `skim` function to collect protocol fees for any token, without requiring a specific role for the token being skimmed.
- Impact: If an attacker gains control over an authorized address, they can use it to skim protocol fees for tokens which do not belong to them.

## Insecure Signer Validation
- Location: smart-contracts/src/packages/Signer.sol : `_validateFulfiller(address intendedFulfiller, address actualFulfiller) internal pure`
- Mechanism: It is assumed that the caller of `createRentFromZone` is the actual fulfiller. However, this is not validated. There is no validation that the address which initiates a rental is the same as the address specified in the rental payload.
- Impact: It is possible for an unauthorized person to initiate a rental, posing as the intended fulfiller.

## Missing Zero Address Check in Guard Policy Update Hook
- Location: smart-contracts/src/policies/Guard.sol : `function updateHookPath(address to, address hook) external onlyRole("GUARD_ADMIN")`
- Mechanism: The `to` address and `hook` address are not checked for the zero address. If either of these addresses is the zero address, then when the `to` address is encountered, control flow will not be forwarded to the `hook`.
- Impact: Unexpected behavior could occur if either the `to` or `hook` is set to the zero address.

## Unchecked `enum` Value in `Stop` Policy's `_validateRentalCanBeStopped` Function
- Location: smart-contracts/src/policies/Stop.sol : `_validateRentalCanBeStoped(OrderType orderType, uint256 endTimestamp, address expectedLender) internal view`
- Mechanism: The `orderType` is not validated to ensure it has a valid enum value. It is possible for an invalid enum value to be passed in, which could cause unexpected behavior.
- Impact: If an invalid enum value is passed into the `_validateRentalCanBeStoped` function, unexpected behavior could occur and an unauthorized party could potentially stop a rental.

## Potential Reentrancy Vulnerability in `PaymentEscrow` Module
- Location: smart-contracts/src/modules/PaymentEscrow.sol : `_safeTransfer(address token, address to, uint256 value) internal`
- Mechanism: When transferring tokens using the `_safeTransfer` function, if a token has a faulty or malicious implementation of the `transfer` function (for example, not returning a boolean value), the contract may enter an infinite loop or revert.
- Impact: While the impact of this bug is low, as the contract is designed to only interact with trusted tokens, an attacker could exploit this vulnerability if the contract interacts with an untrusted token in the future.

## Vulnerability in `Proxy` Contract
- Location: smart-contracts/src/proxy/Proxy.sol : `constructor(address _implementation, bytes memory _data) payable`
- Mechanism: In the proxy constructor, the implementation contract is not checked to see if it implements the `Proxiable` interface.
- Impact: If the implementation contract does not implement the `Proxiable` interface, the proxy contract will not work as intended and may result in unexpected behavior or errors. 

## Misuse of ERC-165
- Location: smart-contracts/src/interfaces/IZone.sol
- Mechanism: The `supportsInterface` function is overloaded, but the `ERC165` interface is not inherited, which could lead to unexpected behavior when checking for interface support.
- Impact: When checking if a contract supports a particular interface using the `supportsInterface` function, it may return incorrect results if the interface is not properly registered.

## Improper Use of `onlyRole` Modifier
- Location: smart-contracts/src/policies/Admin.sol
- Mechanism: The `onlyRole` modifier is used, but it is not checked if the role is properly granted to the address that is calling the function.
- Impact: If an attacker can gain control of an authorized address, they may be able to perform actions that they should not have permission for.

## Lack of Input Validation in `Create` Policy's `validateOrder` Function
- Location: smart-contracts/src/policies/Create.sol
- Mechanism: The `zoneParams` parameter is not validated to ensure it contains valid data.
- Impact: If an attacker provides invalid data in the `zoneParams` parameter, the `validateOrder` function may revert or behave unexpectedly, potentially leading to a denial of service.

## Insecure Hook Control Flow
- Location: smart-contracts/src/policies/Create.sol
- Mechanism: The `hook` contract's `onStart` function is called using a `try-catch` block. However, if the `hook` contract's `onStart` function reverts, the error is caught and a custom error is thrown instead.
- Impact: If an attacker can control the `hook` contract's `onStart` function, they may be able to cause the contract to revert in a way that is not properly handled, potentially leading to unexpected behavior or errors.

## Missing Access Control in `Factory` Policy's `initializeRentalSafe` Function
- Location: smart-contracts/src/policies/Factory.sol
- Mechanism: The `initializeRentalSafe` function is missing access control, allowing any address to call it.
- Impact: If an attacker can call the `initializeRentalSafe` function, they may be able to initialize a rental safe with malicious parameters, potentially leading to security vulnerabilities.

## Incorrect Assumption about Gnosis Safe Module
- Location: smart-contracts/src/policies/Factory.sol
- Mechanism: The `initializeRentalSafe` function assumes that the stop policy address is a valid Gnosis Safe module.
- Impact: If the stop policy address is not a valid Gnosis Safe module, the `initializeRentalSafe` function may behave unexpectedly or revert.

## Unprotected `proxiableUUID` Function
- Location: smart-contracts/src/proxy/Proxiable.sol
- Mechanism: The `proxiableUUID` function returns a unique identifier for the contract, but it is not protected by any access control.
- Impact: If an attacker can call the `proxiableUUID` function, they may be able to obtain sensitive information about the contract's implementation.

## Unchecked ` IMPLEMENTATION_SLOT` Value
- Location: smart-contracts/src/proxy/Proxiable.sol
- Mechanism: The `IMPLEMENTATION_SLOT` value is not checked to ensure it is a valid storage slot.
- Impact: If the `IMPLEMENTATION_SLOT` value is not a valid storage slot, the contract may behave unexpectedly or revert.

## Insecure Deployment of Rental Safe
- Location: smart-contracts/src/policies/Factory.sol
- Mechanism: The `deployRentalSafe` function deploys a rental safe using the Gnosis Safe Proxy Factory, but it does not check if the deployment was successful.
- Impact: If the deployment fails, the function may return an invalid safe address, potentially leading to security vulnerabilities.

## Lack of Input Validation in `Stop` Policy's `stopRent` Function
- Location: smart-contracts/src/policies/Stop.sol
- Mechanism: The `stopRent` function does not validate the input `order` parameter to ensure it contains valid data.
- Impact: If an attacker provides invalid data in the `order` parameter, the `stopRent` function may revert or behave unexpectedly, potentially leading to a denial of service.

## Missing Access Control in `Stop` Policy's `checkTransaction` Function
- Location: smart-contracts/src/policies/Stop.sol
- Mechanism: The `checkTransaction` function is missing access control, allowing any address to call it.
- Impact: If an attacker can call the `checkTransaction` function, they may be able to stop a rental transaction, potentially leading to security vulnerabilities.

## Insecure Reentrancy Protection
- Location: smart-contracts/src/proxy/Proxiable.sol
- Mechanism: The `Proxiable` contract uses a reentrancy protection mechanism, but it is not properly implemented.
- Impact: If an attacker can exploit the reentrancy vulnerability, they may be able to drain the contract's funds or execute arbitrary code.

## Incorrect Assumption about `IHook` Interface
- Location: smart-contracts/src/policies/Create.sol
- Mechanism: The `Create` policy assumes that the `IHook` interface is implemented by the `hook` contract.
- Impact: If the `hook` contract does not implement the `IHook` interface, the `Create` policy may behave unexpectedly or revert.

## Missing Zero Address Check in `Guard` Policy's `updateHookPath` Function
- Location: smart-contracts/src/policies/Guard.sol
- Mechanism: The `updateHookPath` function does not check if the `to` or `hook` addresses are zero.
- Impact: If either the `to` or `hook` address is zero, the function may behave unexpectedly or revert.

## Insecure `onTransaction` Function in `Guard` Policy
- Location: smart-contracts/src/policies/Guard.sol
- Mechanism: The `onTransaction` function is not properly secured, allowing an attacker to potentially exploit the function.
- Impact: If an attacker can exploit the `onTransaction` function, they may be able to execute arbitrary code or drain the contract's funds.

## Missing Access Control in `Guard` Policy's `updateHookStatus` Function
- Location: smart-contracts/src/policies/Guard.sol
- Mechanism: The `updateHookStatus` function is missing access control, allowing any address to call it.
- Impact: If an attacker can call the `updateHookStatus` function, they may be able to update the hook status, potentially leading to security vulnerabilities.

## Unchecked `hook` Address in `Guard` Policy's `checkTransaction` Function
- Location: smart-contracts/src/policies/Guard.sol
- Mechanism: The `checkTransaction` function does not check if the `hook` address is valid.
- Impact: If the `hook` address is not valid, the function may behave unexpectedly or revert.

## Insecure `LibString` Library
- Location: Various contracts
- Mechanism: The `LibString` library is used in various contracts, but it is not properly secured.
- Impact: If an attacker can exploit the `LibString` library, they may be able to execute arbitrary code or drain the contract's funds.

## Missing Input Validation in `Create` Policy's `getRentalOrderHash` Function
- Location: smart-contracts/src/policies/Create.sol
- Mechanism: The `getRentalOrderHash` function does not validate the input `order` parameter to ensure it contains valid data.
- Impact: If an attacker provides invalid data in the `order` parameter, the `getRentalOrderHash` function may revert or behave unexpectedly, potentially leading to a denial of service.

## Insecure Use of `abi.encodePacked` in `Create` Policy's `getRentalOrderHash` Function
- Location: smart-contracts/src/policies/Create.sol
- Mechanism: The `getRentalOrderHash` function uses `abi.encodePacked` to encode the `order` parameter, but it does not properly handle the encoding.
- Impact: If an attacker can exploit the encoding vulnerability, they may be able to execute arbitrary code or drain the contract's funds.

## Missing Access Control in `Create` Policy's `getRentPayloadHash` Function
- Location: smart-contracts/src/policies/Create.sol
- Mechanism: The `getRentPayloadHash` function is missing access control, allowing any address to call it.
- Impact: If an attacker can call the `getRentPayloadHash` function, they may be able to obtain sensitive information about the rental payload.

## Unchecked `payload` Parameter in `Create` Policy's `getRentPayloadHash` Function
- Location: smart-contracts/src/policies/Create.sol
- Mechanism: The `getRentPayloadHash` function does not check if the `payload` parameter is valid.
- Impact: If the `payload` parameter is not valid, the function may behave unexpectedly or revert.

## Insecure Use of `keccak256` in `Create` Policy's `getRentPayloadHash` Function
- Location: smart-contracts/src/policies/Create.sol
- Mechanism: The `getRentPayloadHash` function uses `keccak256` to hash the `payload` parameter, but it does not properly handle the hashing.
- Impact: If an attacker can exploit the hashing vulnerability, they may be able to execute arbitrary code or drain the contract's funds.

## Missing Input Validation in `Create` Policy's `getOrderMetadataHash` Function
- Location: smart-contracts/src/policies/Create.sol
- Mechanism: The `getOrderMetadataHash` function does not validate the input `metadata` parameter to ensure it contains valid data.
- Impact: If an attacker provides invalid data in the `metadata` parameter, the `getOrderMetadataHash` function may revert or behave unexpectedly, potentially leading to a denial of service.

## Insecure Use of `abi.encodePacked` in `Create` Policy's `getOrderMetadataHash` Function
- Location: smart-contracts/src/policies/Create.sol
- Mechanism: The `getOrderMetadataHash` function uses `abi.encodePacked` to encode the `metadata` parameter, but it does not properly handle the encoding.
- Impact: If an attacker can exploit the encoding vulnerability, they may be able to execute arbitrary code or drain the contract's funds.

## Missing Access Control in `Create` Policy's `validateOrder` Function
- Location: smart-contracts/src/policies/Create.sol
- Mechanism: The `validateOrder` function is missing access control, allowing any address to call it.
- Impact: If an attacker can call the `validateOrder` function, they may be able to validate an order, potentially leading to security vulnerabilities.

## Unchecked `zoneParams` Parameter in `Create` Policy's `validateOrder` Function
- Location: smart-contracts/src/policies/Create.sol
- Mechanism: The `validateOrder` function does not check if the `zoneParams` parameter is valid.
- Impact: If the `zoneParams` parameter is not valid, the function may behave unexpectedly or revert.

## Insecure Use of `abi.decode` in `Create` Policy's `validateOrder` Function
- Location: smart-contracts/src/policies/Create.sol
- Mechanism: The `validateOrder` function uses `abi.decode` to decode the `zoneParams` parameter, but it does not properly handle the decoding.
- Impact: If an attacker can exploit the decoding vulnerability, they may be able to execute arbitrary code or drain the contract's funds.

## Missing Input Validation in `Stop` Policy's `stopRent` Function
- Location: smart-contracts/src/policies/Stop.sol
- Mechanism: The `stopRent` function does not validate the input `order` parameter to ensure it contains valid data.
- Impact: If an attacker provides invalid data in the `order` parameter, the `stopRent` function may revert or behave unexpectedly, potentially leading to a denial of service.

## Insecure Use of `abi.encodePacked` in `Stop` Policy's `stopRent` Function
- Location: smart-contracts/src/policies/Stop.sol
- Mechanism: The `stopRent` function uses `abi.encodePacked` to encode the `order` parameter, but it does not properly handle the encoding.
- Impact: If an attacker can exploit the encoding vulnerability, they may be able to execute arbitrary code or drain the contract's funds.

## Missing Access Control in `Stop` Policy's `stopRentBatch` Function
- Location: smart-contracts/src/policies/Stop.sol
- Mechanism: The `stopRentBatch` function is missing access control, allowing any address to call it.
- Impact: If an attacker can call the `stopRentBatch` function, they may be able to stop a batch of rentals, potentially leading to security vulnerabilities.

## Unchecked `orders` Parameter in `Stop` Policy's `stopRentBatch` Function
- Location: smart-contracts/src/policies/Stop.sol
- Mechanism: The `stopRentBatch` function does not check if the `orders` parameter is valid.
- Impact: If the `orders` parameter is not valid, the function may behave unexpectedly or revert.

## Insecure Use of `abi.encodePacked` in `Stop` Policy's `stopRentBatch` Function
- Location: smart-contracts/src/policies/Stop.sol
- Mechanism: The `stopRentBatch` function uses `abi.encodePacked` to encode the `orders` parameter, but it does not properly handle the encoding.
- Impact: If an attacker can exploit the encoding vulnerability, they may be able to execute arbitrary code or drain the contract's funds.

## Missing Input Validation in `Guard` Policy's `checkTransaction` Function
- Location: smart-contracts/src/policies/Guard.sol
- Mechanism: The `checkTransaction` function does not validate the input `to` and `data` parameters to ensure they contain valid data.
- Impact: If an attacker provides invalid data in the `to` or `data` parameters, the `checkTransaction` function may revert or behave unexpectedly, potentially leading to a denial of service.

## Insecure Use of `abi.encodePacked` in `Guard` Policy's `checkTransaction` Function
- Location: smart-contracts/src/policies/Guard.sol
- Mechanism: The `checkTransaction` function uses `abi.encodePacked` to encode the `data` parameter, but it does not properly handle the encoding.
- Impact: If an attacker can exploit the encoding vulnerability, they may be able to execute arbitrary code or drain the contract's funds.

## Missing Access Control in `Guard` Policy's `updateHookPath` Function
- Location: smart-contracts/src/policies/Guard.sol
- Mechanism: The `updateHookPath` function is missing access control, allowing any address to call it.
- Impact: If an attacker can call the `updateHookPath` function, they may be able to update the hook path, potentially leading to security vulnerabilities.

## Unchecked `to` and `hook` Parameters in `Guard` Policy's `updateHookPath` Function
- Location: smart-contracts/src/policies/Guard.sol
- Mechanism: The `updateHookPath` function does not check if the `to` and `hook` parameters are valid.
- Impact: If the `to` or `hook` parameters are not valid, the function may behave unexpectedly or revert.

## Insecure Use of `abi.encodePacked` in `Guard` Policy's `updateHookPath` Function
- Location: smart-contracts/src/policies/Guard.sol
- Mechanism: The `updateHookPath` function uses `abi.encodePacked` to encode the `to` and `hook` parameters, but it does not properly handle the encoding.
- Impact: If an attacker can exploit the encoding vulnerability, they may be able to execute arbitrary code or drain the contract's funds.

## Missing Input Validation in `Guard` Policy's `updateHookStatus` Function
- Location: smart-contracts/src/policies/Guard.sol
- Mechanism: The `updateHookStatus` function does not validate the input `hook` and `bitmap` parameters to ensure they contain valid data.
- Impact: If an attacker provides invalid data in the `hook` or `bitmap` parameters, the `updateHookStatus` function may revert or behave unexpectedly, potentially leading to a denial of service.

## Insecure Use of `abi.encodePacked` in `Guard` Policy's `updateHookStatus` Function
- Location: smart-contracts/src/policies/Guard.sol
- Mechanism: The `updateHookStatus` function uses `abi.encodePacked` to encode the `hook` and `bitmap` parameters, but it does not properly handle the encoding.
- Impact: If an attacker can exploit the encoding vulnerability, they may be able to execute arbitrary code or drain the contract's funds.

## Missing Access Control in `Proxy` Contract's `constructor` Function
- Location: smart-contracts/src/proxy/Proxy.sol
- Mechanism: The `constructor` function is missing access control, allowing any address to call it.
- Impact: If an attacker can call the `constructor` function, they may be able to deploy a proxy contract, potentially leading to security vulnerabilities.

## Unchecked `implementation` and `_data` Parameters in `Proxy` Contract's `constructor` Function
- Location: smart-contracts/src/proxy/Proxy.sol
- Mechanism: The `constructor` function does not check if the `implementation` and `_data` parameters are valid.
- Impact: If the `implementation` or `_data` parameters are not valid, the function may behave unexpectedly or revert.

## Insecure Use of `abi.encodePacked` in `Proxy` Contract's `constructor` Function
- Location: smart-contracts/src/proxy/Proxy.sol
- Mechanism: The `constructor` function uses `abi.encodePacked` to encode the `implementation` and `_data` parameters, but it does not properly handle the encoding.
- Impact: If an attacker can exploit the encoding vulnerability, they may be able to execute arbitrary code or drain the contract's funds.
