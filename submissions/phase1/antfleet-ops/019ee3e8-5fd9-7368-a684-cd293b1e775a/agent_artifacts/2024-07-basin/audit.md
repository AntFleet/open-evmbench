# Audit: 2024-07-basin

## <Invalid Well Configuration>
- Location: src/Aquifer.sol : `function boreWell`
- Mechanism: 
  In line 73, the call to `initFunctionCall(msg.sender, amountIn, amountIn)` can potentially revert if
  `initFunctionCall` is a function that can only be called when not initialized. This could cause a loss of funds
  as well as reserves if used to (re)initialize a Well that has already been initialized.
  The underlying function for initialization should have implemented the logic to prevent multiple initializations.
- Impact: 
  An attacker could drain the liquidity of the Well as well as burn the assets prior to initializing the well. This is done by calling `boreWell` with
  a large balance, an amountIn, and a corresponding `initFunctionCall` and appropriately constructed auxiliary args.

## <Unsecured Well>
- Location: src/Well.sol : `function _updatePumps`
- Mechanism: 
  In line 416 of `function _updatePumps` of `Well.sol` the `_updatePumps` tries `IPump(_pump.target).update` on a set of pumps but it will fail 
  if the update call reverts.
  However, the error is simply ignored if such an error occurs.
  By doing so, if the revert happens, participants in the protocol may incorrectly be able to perform certain actions, 
  leading to a security issue.
- Impact: 
  An actor may use the pump to drain the well's tokens, or a critical pump could silently not get to execute a 
  critical update and lead to unintended issues

## <Massive [Un]optimised executions>
- Location: src/WellUpgradeable.sol : `predictWellAddress`
- Mechanism: 
  In the predictWellAddress function of the WellUpgradeable
  contract, there is a potential bug with the usage of the `salt` parameter.
  The predictWellAddress is calculating the well address based on a provided
  salt value.
  If this salt is set to zero, the function reverts stating that this is an 
  invalid salt.
  To preempt this from happening, we can set the `salt` value 
  to a different value.
- Impact: 
  This function will return the deployment address of the well that is created
  from a given set of constructor arguments on Etherscan.

## <Unsecured direct external calls>
- Location: src/Aquifer.sol : `function boreWell`
- Mechanism: 
  In the course of the execution of `boreWell` function, and the call to the newly deployed well.
  The well has access to the current `msg.sender` balance (via the calldata), which may cause unintended behavior.
- Impact: 
  In this scenario, attackers may send malicious requests to manipulate funds or other system behaviors in the
  deployed well account.

## <Insufficient Input Validation>
- Location: src/libraries/LibBytes16.sol : `storeBytes16` and `readBytes16`
- Mechanism: 
  In these functions, for odd-length arrays of bytes16, an extra bytes16 slot is used; but the lowest 8 bits of the 
  last bytes16 (which are the highest bits of the slot) are ignored in the read function (i.e. not propagated back 
  to the slot during writing).
  Thus, part of that 8 bits will be truncated with no notice.
- Impact: 
  If the user employs the lowest bit utilized by the programme for required data,
  sufficient damage would ensue.
