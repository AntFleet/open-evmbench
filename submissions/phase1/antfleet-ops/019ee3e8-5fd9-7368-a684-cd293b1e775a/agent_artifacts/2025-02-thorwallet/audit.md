# Audit: 2025-02-thorwallet

### 1. Missing Access Control in `onTokenTransfer`
- Location: `MergeTgt.sol` : `onTokenTransfer`
- Mechanism: The `onTokenTransfer` function does not check if the sender has any TGT tokens approved for the contract, allowing an attacker to bypass the approval mechanism.
- Impact: An attacker can trigger the `onTokenTransfer` function without sending any TGT tokens, potentially draining the contract's TITN balance.

### 2. Lack of Input Validation in `quoteTitn`
- Location: `MergeTgt.sol` : `quoteTitn`
- Mechanism: The `quoteTitn` function does not validate the input `tgtAmount`, which can lead to division by zero or incorrect calculations.
- Impact: An attacker can pass a large `tgtAmount` to the `quoteTitn` function, causing incorrect calculations and potentially draining the contract's TITN balance.

### 3. Potential Reentrancy in `withdrawRemainingTitn`
- Location: `MergeTgt.sol` : `withdrawRemainingTitn`
- Mechanism: The `withdrawRemainingTitn` function calls the `titn.safeTransfer` function, which can potentially trigger a reentrancy attack if the recipient contract reenters the `withdrawRemainingTitn` function.
- Impact: An attacker can reenter the `withdrawRemainingTitn` function, potentially draining the contract's TITN balance.

### 4. Missing Access Control in `setTransferAllowedContract`
- Location: `Titn.sol` : `setTransferAllowedContract`
- Mechanism: The `setTransferAllowedContract` function does not check if the new transfer allowed contract has any restrictions or approvals in place.
- Impact: An attacker can set a new transfer allowed contract that has no restrictions or approvals, potentially allowing unrestricted transfers of TITN tokens.

### 5. Potential Race Condition in `withdrawRemainingTitn`
- Location: `MergeTgt.sol` : `withdrawRemainingTitn`
- Mechanism: The `withdrawRemainingTitn` function calculates the `userProportionalShare` based on the current `remainingTitnAfter1Year` and `initialTotalClaimable` values, which can be changed by other users or contracts before the calculation is completed.
- Impact: An attacker can manipulate the `remainingTitnAfter1Year` or `initialTotalClaimable` values, potentially altering the calculated `userProportionalShare` and affecting the amount of TITN tokens transferred to the user.

### 6. Lack of Event Emission in `quoteTitn`
- Location: `MergeTgt.sol` : `quoteTitn`
- Mechanism: The `quoteTitn` function does not emit an event when the quote is calculated, making it difficult to track and monitor the quote calculations.
- Impact: An attacker can manipulate the quote calculations without being detected, potentially affecting the amount of TITN tokens transferred to users.

### 7. Missing Access Control in `setBridgedTokenTransferLocked`
- Location: `Titn.sol` : `setBridgedTokenTransferLocked`
- Mechanism: The `setBridgedTokenTransferLocked` function does not check if the new bridged token transfer locked status has any restrictions or approvals in place.
- Impact: An attacker can set the bridged token transfer locked status to false, potentially allowing unrestricted transfers of TITN tokens.

### 8. Potential Reentrancy in `transfer` and `transferFrom` of `Titn` contract
- Location: `Titn.sol` : `transfer` and `transferFrom`
- Mechanism: The `transfer` and `transferFrom` functions in the `Titn` contract call the `super.transfer` and `super.transferFrom` functions, which can potentially trigger a reentrancy attack if the recipient contract reenters the `transfer` or `transferFrom` function.
- Impact: An attacker can reenter the `transfer` or `transferFrom` function, potentially draining the contract's TITN balance.

### 9. Missing Validation in `_validateTransfer` function
- Location: `Titn.sol` : `_validateTransfer`
- Mechanism: The `_validateTransfer` function does not validate if the `from` or `to` addresses are valid or if the `amount` is valid.
- Impact: An attacker can pass invalid addresses or amounts to the `_validateTransfer` function, potentially causing the function to fail or behave unexpectedly.

### 10. Potential Race Condition in `_credit` function
- Location: `Titn.sol` : `_credit`
- Mechanism: The `_credit` function mints new tokens to the recipient address, but does not check if the recipient address has any existing balance or restrictions.
- Impact: An attacker can manipulate the recipient address's balance or restrictions before the `_credit` function is completed, potentially affecting the amount of tokens minted or transferred.
