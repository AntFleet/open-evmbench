# Audit: 2024-08-phi

# Vulnerabilities in the Solidity Code

## 1. Reentrancy Vulnerability
- **Location:** `src/Cred.sol` : `_handleTrade`, `PhiNFT1155.sol` : `claimFromFactory`
- **Mechanism:** The contracts use the `safeTransferETH` function to transfer Ether, but they also call external contracts (`IBondingCurve` and `IPhiRewards`) before making the transfer. An attacker could exploit this by reentering the contract and draining its funds.
- **Impact:** An attacker can drain the contract's funds by reentering it and making it transfer more Ether than intended.

## 2. Unprotected Function
- **Location:** `src/Cred.sol` : `setPhiSignerAddress`, `setProtocolFeeDestination`, `setProtocolFeePercent`, `setPhiRewardsAddress`
- **Mechanism:** The functions are only protected by the `onlyOwner` modifier, but an attacker could exploit the contract if they gain ownership of it.
- **Impact:** An attacker can change the contract's settings if they gain ownership of it.

## 3. Unvalidated Input
- **Location:** `src/Cred.sol` : `createCred`, `updateCred`
- **Mechanism:** The functions do not validate the input data, which could lead to unexpected behavior or errors.
- **Impact:** An attacker can provide malformed input data to cause unexpected behavior or errors.

## 4. Use of Tx.origin
- **Location:** `src/PhiFactory.sol` : `_validateAndUpdateClaimState`
- **Mechanism:** The contract uses `tx.origin` to check the sender of the transaction, but this can be vulnerable to phishing attacks.
- **Impact:** An attacker can use phishing attacks to trick users into making unintended transactions.

## 5. Missing Input Validation
- **Location:** `src/PhiFactory.sol` : `claim`, `batchClaim`
- **Mechanism:** The functions do not validate the input data, which could lead to unexpected behavior or errors.
- **Impact:** An attacker can provide malformed input data to cause unexpected behavior or errors.

## 6. Incorrect Use of Arithmetic Operations
- **Location:** `src/BondingCurve.sol` : `_curve`
- **Mechanism:** The function uses arithmetic operations that can cause overflows or underflows.
- **Impact:** An attacker can exploit the contract by causing overflows or underflows, leading to unexpected behavior.

## 7. Unprotected Function
- **Location:** `src/PhiNFT1155.sol` : `updateRoyalties`
- **Mechanism:** The function is only protected by the `onlyArtCreator` modifier, but an attacker could exploit the contract if they gain the art creator role.
- **Impact:** An attacker can update the royalties if they gain the art creator role.

## 8. Missing Event Emission
- **Location:** `src/Cred.sol` : `_updateCuratorShareBalance`
- **Mechanism:** The function does not emit an event when updating the curator's share balance.
- **Impact:** Users may not be notified of changes to their share balances.

The above findings highlight potential issues in the provided Solidity contracts, including reentrancy vulnerabilities, unprotected functions, unvalidated input, and missing event emissions. To mitigate these risks, consider implementing proper access controls, input validation, and event emission mechanisms. Additionally, conduct regular security audits and testing to ensure the contracts' integrity and security.
