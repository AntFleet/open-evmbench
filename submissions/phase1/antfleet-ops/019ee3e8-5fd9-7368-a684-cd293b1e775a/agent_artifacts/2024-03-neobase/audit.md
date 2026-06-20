# Audit: 2024-03-neobase

## 1. Unprotected Function
- Location: `LendingLedger.sol` : `sync_ledger` function
- Mechanism: The `sync_ledger` function is called by the lending market on cNOTE deposits/withdrawals, but it does not check whether the `msg.sender` is a whitelisted lending market or not. This could allow a malicious contract to call this function and potentially manipulate the user's reward debt or market balance.
- Impact: An attacker could manipulate the user's reward debt or market balance by calling the `sync_ledger` function with a non-zero `_delta` value.

## 2. Unsecured Use of `transfer`
- Location: `LendingLedger.sol` : `claim` function
- Mechanism: The `claim` function uses the `call` function to send CANTO to the user, but it does not check the return value of the `call`. If the user is a contract, it could potentially revert the transaction.
- Impact: An attacker could potentially revert the transaction and steal the CANTO by implementing a fallback function in their contract that always reverts.

## 3. Unprotected Function
- Location: `GaugeController.sol` : `checkpoint` function
- Mechanism: The `checkpoint` function is not restricted to any specific role or address, which means anyone can call it and trigger the checkpoint. 
- Impact: An attacker could potentially call the `checkpoint` function repeatedly, causing unnecessary computations and potentially leading to a denial-of-service attack.

## 4. Unprotected Function
- Location: `GaugeController.sol` : `checkpoint_gauge` function
- Mechanism: The `checkpoint_gauge` function is not restricted to any specific role or address, which means anyone can call it and trigger the checkpoint for a specific gauge. 
- Impact: An attacker could potentially call the `checkpoint_gauge` function repeatedly for a specific gauge, causing unnecessary computations and potentially leading to a denial-of-service attack.

## 5. Unsecured Use of Arithmetic Operations
- Location: `VotingEscrow.sol` : Various functions
- Mechanism: The `VotingEscrow` contract uses several arithmetic operations, such as addition, subtraction, and multiplication, without checking for potential overflows or underflows.
- Impact: An attacker could potentially exploit these operations to cause unintended behavior or revert the transaction.

## 6. Unsecured Use of `call` Function
- Location: `VotingEscrow.sol` : `withdraw` function
- Mechanism: The `withdraw` function uses the `call` function to send CANTO to the user, but it does not check the return value of the `call`. If the user is a contract, it could potentially revert the transaction.
- Impact: An attacker could potentially revert the transaction and steal the CANTO by implementing a fallback function in their contract that always reverts.

## 7. Lack of Input Validation
- Location: `LendingLedger.sol` : `setRewards` function
- Mechanism: The `setRewards` function does not validate the input `_fromEpoch` and `_toEpoch` to ensure they are within a valid range.
- Impact: An attacker could potentially set rewards for an invalid epoch, causing unintended behavior or revert the transaction.

## 8. Lack of Input Validation
- Location: `LendingLedger.sol` : `whiteListLendingMarket` function
- Mechanism: The `whiteListLendingMarket` function does not validate the input `_market` to ensure it is a valid lending market.
- Impact: An attacker could potentially whitelist an invalid lending market, causing unintended behavior or revert the transaction.

## 9. Lack of Reentrancy Protection
- Location: `LiquidityGauge.sol` : `_afterTokenTransfer` function
- Mechanism: The `_afterTokenTransfer` function calls the `sync_ledger` function of the `LendingLedger` contract, but it does not use reentrancy protection.
- Impact: An attacker could potentially reenter the `_afterTokenTransfer` function, causing unintended behavior or stealing funds.

## 10. Unprotected Function
- Location: `GaugeController.sol` : `vote_for_gauge_weights` function
- Mechanism: The `vote_for_gauge_weights` function does not restrict the `msg.sender` to a specific role or address.
- Impact: An attacker could potentially call the `vote_for_gauge_weights` function and manipulate the gauge weights.
