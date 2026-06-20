# Audit: 2024-07-munchables

# Unprotected Function

## <Unprotected configUpdated function>
- Location: `src/managers/AccountManager.sol` : `function configUpdated() external override onlyConfigStorage`
- Mechanism: The `configUpdated` function is not properly protected, allowing any user to update the configuration by calling this function. This could potentially lead to unintended behavior or security vulnerabilities.
- Impact: An attacker could exploit this function to update the configuration of the `AccountManager` contract, potentially causing disruptions to the normal operation of the contract or even leading to financial losses.

## <Unprotected configUpdated function>
- Location: `src/managers/BaseBlastManager.sol` : `function configUpdated() external override onlyConfigStorage`
- Mechanism: The `configUpdated` function is not properly protected, allowing any user to update the configuration by calling this function. This could potentially lead to unintended behavior or security vulnerabilities.
- Impact: An attacker could exploit this function to update the configuration of the `BaseBlastManager` contract, potentially causing disruptions to the normal operation of the contract or even leading to financial losses.

## <Unprotected configUpdated function>
- Location: `src/managers/LockManager.sol` : `function configUpdated() external override onlyConfigStorage`
- Mechanism: The `configUpdated` function is not properly protected, allowing any user to update the configuration by calling this function. This could potentially lead to unintended behavior or security vulnerabilities.
- Impact: An attacker could exploit this function to update the configuration of the `LockManager` contract, potentially causing disruptions to the normal operation of the contract or even leading to financial losses.

## <Unprotected configUpdated function>
- Location: `src/managers/MigrationManager.sol` : `function configUpdated() external override onlyConfigStorage`
- Mechanism: The `configUpdated` function is not properly protected, allowing any user to update the configuration by calling this function. This could potentially lead to unintended behavior or security vulnerabilities.
- Impact: An attacker could exploit this function to update the configuration of the `MigrationManager` contract, potentially causing disruptions to the normal operation of the contract or even leading to financial losses.

## <Unprotected configUpdated function>
- Location: `src/managers/MunchadexManager.sol` : `function configUpdated() external override onlyConfigStorage`
- Mechanism: The `configUpdated` function is not properly protected, allowing any user to update the configuration by calling this function. This could potentially lead to unintended behavior or security vulnerabilities.
- Impact: An attacker could exploit this function to update the configuration of the `MunchadexManager` contract, potentially causing disruptions to the normal operation of the contract or even leading to financial losses.

## <Unprotected configUpdated function>
- Location: `src/managers/NFTAttributeManagerV1.sol` : `function configUpdated() external override onlyConfigStorage`
- Mechanism: The `configUpdated` function is not properly protected, allowing any user to update the configuration by calling this function. This could potentially lead to unintended behavior or security vulnerabilities.
- Impact: An attacker could exploit this function to update the configuration of the `NFTAttributeManagerV1` contract, potentially causing disruptions to the normal operation of the contract or even leading to financial losses.

## <Unprotected configUpdated function>
- Location: `src/managers/PrimordialManager.sol` : `function configUpdated() external override onlyConfigStorage`
- Mechanism: The `configUpdated` function is not properly protected, allowing any user to update the configuration by calling this function. This could potentially lead to unintended behavior or security vulnerabilities.
- Impact: An attacker could exploit this function to update the configuration of the `PrimordialManager` contract, potentially causing disruptions to the normal operation of the contract or even leading to financial losses.

## <Unprotected configUpdated function>
- Location: `src/managers/RewardsManager.sol` : `function configUpdated() external override onlyConfigStorage`
- Mechanism: The `configUpdated` function is not properly protected, allowing any user to update the configuration by calling this function. This could potentially lead to unintended behavior or security vulnerabilities.
- Impact: An attacker could exploit this function to update the configuration of the `RewardsManager` contract, potentially causing disruptions to the normal operation of the contract or even leading to financial losses.

## <Unprotected configUpdated function>
- Location: `src/managers/SnuggeryManager.sol` : `function configUpdated() external override onlyConfigStorage`
- Mechanism: The `configUpdated` function is not properly protected, allowing any user to update the configuration by calling this function. This could potentially lead to unintended behavior or security vulnerabilities.
- Impact: An attacker could exploit this function to update the configuration of the `SnuggeryManager` contract, potentially causing disruptions to the normal operation of the contract or even leading to financial losses.

## <Unprotected provideRandom function>
- Location: `src/rng/RNGProxySelfHosted.sol` : `function provideRandom(uint256 _index, bytes calldata _rand) external onlyRole(Role.NFTOracle)`
- Mechanism: The `provideRandom` function is not properly protected, allowing the `NFTOracle` role to provide random numbers without proper validation. This could potentially lead to unintended behavior or security vulnerabilities.
- Impact: An attacker with the `NFTOracle` role could exploit this function to provide malicious random numbers, potentially causing disruptions to the normal operation of the contract or even leading to financial losses.

# Reentrancy

## <Reentrancy vulnerability in importMunchable function>
- Location: `src/managers/SnuggeryManager.sol` : `function importMunchable(uint256 _tokenId) external notPaused chonkUpdated`
- Mechanism: The `importMunchable` function is vulnerable to reentrancy attacks, as it calls the `transferFrom` function of the `IERC721` token contract before updating the state of the `SnuggeryManager` contract.
- Impact: An attacker could exploit this vulnerability to reenter the `importMunchable` function, potentially causing unintended behavior or security vulnerabilities.

## <Reentrancy vulnerability in exportMunchable function>
- Location: `src/managers/SnuggeryManager.sol` : `function exportMunchable(uint256 _tokenId) external notPaused chonkUpdated`
- Mechanism: The `exportMunchable` function is vulnerable to reentrancy attacks, as it calls the `transferFrom` function of the `IERC721` token contract before updating the state of the `SnuggeryManager` contract.
- Impact: An attacker could exploit this vulnerability to reenter the `exportMunchable` function, potentially causing unintended behavior or security vulnerabilities.

## <Reentrancy vulnerability in lock function>
- Location: `src/managers/LockManager.sol` : `function lock(address _tokenContract, uint256 _quantity) external payable notPaused onlyActiveToken(_tokenContract) onlyConfiguredToken(_tokenContract) nonReentrant`
- Mechanism: The `lock` function is vulnerable to reentrancy attacks, as it calls the `transferFrom` function of the `IERC20` token contract before updating the state of the `LockManager` contract.
- Impact: An attacker could exploit this vulnerability to reenter the `lock` function, potentially causing unintended behavior or security vulnerabilities.

## <Reentrancy vulnerability in unlock function>
- Location: `src/managers/LockManager.sol` : `function unlock(address _tokenContract, uint256 _quantity) external notPaused nonReentrant`
- Mechanism: The `unlock` function is vulnerable to reentrancy attacks, as it calls the `transfer` function of the `IERC20` token contract before updating the state of the `LockManager` contract.
- Impact: An attacker could exploit this vulnerability to reenter the `unlock` function, potentially causing unintended behavior or security vulnerabilities.

# Unsecured Use of Tx.origin

## <Unsecured use of tx.origin in burn function>
- Location: `src/tokens/OldMunchNFT.sol` : `function burn(uint256 _tokenId) public onlyMigrationManager`
- Mechanism: The `burn` function uses `tx.origin` to check if the caller is the `migrationManager`, which is not secure as it can be tampered with by an attacker.
- Impact: An attacker could exploit this vulnerability to burn tokens without being the `migrationManager`, potentially causing financial losses.

#Use of Obsolete Solidity Version

## <Use of obsolete Solidity version>
- Location: `src/tokens/OldMunchNFTTest.sol`
- Mechanism: The contract is using an obsolete version of Solidity (0.8.20), which may contain known security vulnerabilities.
- Impact: The contract may be vulnerable to known security exploits, potentially causing unintended behavior or security vulnerabilities.

# Missing Zero Address Check

## <Missing zero address check in setTokenURI function>
- Location: `src/tokens/MunchNFT.sol` : `function setTokenURI(uint256 _tokenId, string memory _tokenURI) external onlyRole(Role.NFTOracle)`
- Mechanism: The `setTokenURI` function does not check if the `_tokenURI` is a zero address, which could potentially lead to errors or security vulnerabilities.
- Impact: An attacker could exploit this vulnerability to set a zero address as the token URI, potentially causing unintended behavior or security vulnerabilities.

## <Missing zero address check in setMigrationManager function>
- Location: `src/tokens/OldMunchNFT.sol` : `function setMigrationManager(address _migrationManager) external onlyRole(DEFAULT_ADMIN_ROLE)`
- Mechanism: The `setMigrationManager` function does not check if the `_migrationManager` is a zero address, which could potentially lead to errors or security vulnerabilities.
- Impact: An attacker could exploit this vulnerability to set a zero address as the migration manager, potentially causing unintended behavior or security vulnerabilities.

# Inconsistent Naming Conventions

## <Inconsistent naming conventions>
- Location: Throughout the codebase
- Mechanism: The codebase uses both camelCase and underscore notation for variable and function names, which can make the code harder to read and maintain.
- Impact: The inconsistent naming conventions can make it more difficult for developers to understand and modify the code, potentially leading to errors or security vulnerabilities.

# Outdated Comments

## <Outdated comments>
- Location: Throughout the codebase
- Mechanism: Some comments in the codebase are outdated and do not reflect the current functionality of the code.
- Impact: The outdated comments can make it more difficult for developers to understand the code, potentially leading to errors or security vulnerabilities.

# Magic Numbers

## <Magic numbers>
- Location: Throughout the codebase
- Mechanism: The codebase uses magic numbers (e.g., `100`, `1000`, etc.) without explanation, which can make the code harder to understand and maintain.
- Impact: The magic numbers can make it more difficult for developers to understand the code, potentially leading to errors or security vulnerabilities.

# Redundant Code

## <Redundant code>
- Location: Throughout the codebase
- Mechanism: Some code in the codebase is redundant and can be removed without affecting the functionality of the contract.
- Impact: The redundant code can make the codebase larger and more difficult to maintain, potentially leading to errors or security vulnerabilities.

# Complex Conditional Statements

## <Complex conditional statements>
- Location: Throughout the codebase
- Mechanism: Some conditional statements in the codebase are complex and difficult to understand, which can make the code harder to maintain and potentially lead to errors or security vulnerabilities.
- Impact: The complex conditional statements can make it more difficult for developers to understand and modify the code, potentially leading to errors or security vulnerabilities.
