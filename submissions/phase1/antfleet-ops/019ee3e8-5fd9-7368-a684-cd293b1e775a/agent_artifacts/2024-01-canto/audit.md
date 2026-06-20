# Audit: 2024-01-canto

## 1. Reentrancy in `LendingLedger` Contract
- Location: LendingLedger.sol : `sync_ledger` function
- Mechanism: The `sync_ledger` function in the `LendingLedger` contract calls the `update_market` function, which in turn calls the `gaugeController.gauge_relative_weight_write` function. This function can potentially trigger a reentrancy attack if the `gaugeController` contract is not properly secured, as it makes an external call.
- Impact: An attacker could potentially drain the contract by repeatedly calling the `sync_ledger` function and manipulating the external call to `gauge_relative_weight_write`.

## 2. Unprotected Function in `GaugeController` Contract
- Location: GaugeController.sol : `remove_gauge_weight` function
- Mechanism: The `remove_gauge_weight` function is declared as `public` and does not have any access control modifiers, making it accessible to anyone. This could lead to unintended removal of gauge weights.
- Impact: An attacker could remove gauge weights without authorization, potentially disrupting the intended functionality of the contract.

## 3. Potential Division by Zero in `LendingLedger` Contract
- Location: LendingLedger.sol : `update_market` function
- Mechanism: In the `update_market` function, the `marketSupply` variable is used as a divisor to calculate `cantoReward` and update `market.secRewardsPerShare`. If `marketSupply` is zero, this will result in a division by zero error.
- Impact: A division by zero error could occur if `marketSupply` is zero, potentially causing the contract to fail or behave unexpectedly.

## 4. Potential Underflow in `LendingLedger` Contract
- Location: LendingLedger.sol : `sync_ledger` function
- Mechanism: The `lendingMarketTotalBalance` variable is updated by subtracting `_delta` from it. If `_delta` is greater than the current balance, this could result in an underflow.
- Impact: An underflow could occur if `_delta` is greater than the current `lendingMarketTotalBalance`, potentially causing the contract to fail or behave unexpectedly.

## 5. Use of `transfer` in `LendingLedger` Contract
- Location: LendingLedger.sol : `claim` function
- Mechanism: The `claim` function uses the `transfer` function to send CANTO to the user. However, the `transfer` function can fail if the recipient contract does not support receiving Ether.
- Impact: The use of `transfer` could result in failed transactions if the recipient contract does not support receiving Ether.

## 6. Missing Input Validation in `GaugeController` Contract
- Location: GaugeController.sol : `vote_for_gauge_weights` function
- Mechanism: The `vote_for_gauge_weights` function does not validate the `_user_weight` input. If `_user_weight` is greater than the maximum allowed value, this could result in unexpected behavior.
- Impact: Unexpected behavior could occur if `_user_weight` is not validated, potentially causing the contract to fail or behave unexpectedly.

## 7. Potential Integer Overflow in `GaugeController` Contract
- Location: GaugeController.sol : `_get_sum` function
- Mechanism: The `_get_sum` function uses a loop to calculate the sum of weights. However, the loop counter `i` is not validated, which could result in an integer overflow if the loop runs for a large number of iterations.
- Impact: An integer overflow could occur if the loop runs for a large number of iterations, potentially causing the contract to fail or behave unexpectedly.

## 8. Missing Access Control in `VotingEscrow` Contract
- Location: VotingEscrow.sol : `checkpoint` function
- Mechanism: The `checkpoint` function does not have any access control modifiers, making it accessible to anyone. This could lead to unintended checkpointing of the contract state.
- Impact: An attacker could call the `checkpoint` function repeatedly, potentially disrupting the intended functionality of the contract.

## 9. Use of `now` in `VotingEscrow` Contract
- Location: VotingEscrow.sol : `createLock` function
- Mechanism: The `createLock` function uses the `now` keyword to access the current timestamp. However, `now` can be manipulated by miners, which could result in unexpected behavior.
- Impact: Unexpected behavior could occur if `now` is manipulated by miners, potentially causing the contract to fail or behave unexpectedly.

## 10. Missing Event Emission in `VotingEscrow` Contract
- Location: VotingEscrow.sol : `withdraw` function
- Mechanism: The `withdraw` function does not emit an event when the withdrawal is successful. This could make it difficult to track the contract's state.
- Impact: The lack of event emission could make it difficult to track the contract's state, potentially causing issues with contract management and auditing.
