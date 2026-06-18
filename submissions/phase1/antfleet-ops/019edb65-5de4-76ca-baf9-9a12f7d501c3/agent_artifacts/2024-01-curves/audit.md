# Audit: 2024-01-curves

## Broken access control in Security modifiers
- Location: `contracts/Security.sol` : `onlyOwner`, `onlyManager`
- Mechanism: The modifiers are defined as `msg.sender == owner;` and `managers[msg.sender] == true;` without any `require()` or `revert()`. In Solidity, a bare boolean expression does not revert – it simply evaluates and is discarded. Consequently these modifiers never block execution, and every function guarded by `onlyOwner` or `onlyManager` is effectively public.
- Impact: An attacker can seize ownership (`transferOwnership`), appoint managers (`setManager`), change the protocol fee destination and percentages, replace the ERC20 factory with a malicious contract, and redirect the fee redistributor. This gives complete control over all funds and economics of the protocol.

## Permanent loss of holder fees on every buy/sell
- Location: `contracts/Curves.sol` : `_transferFees` → `contracts/FeeSplitter.sol` : `onBalanceChange`
- Mechanism: During any trade, `_transferFees` calls `feeRedistributor.onBalanceChange(curvesTokenSubject, msg.sender)`. This function sets the user’s `userFeeOffset` to the current `cumulativeFeePerToken` *without* first calling `updateFeeCredit()` to transfer pending fees into `unclaimedFees`. Because the offset is moved forward without credit, all holder fees that had accrued for the user up to that point are erased. This happens on every single buy or sell.
- Impact: Every token holder loses their entire unclaimed fee balance every time they trade. Over repeated trades, all fee rewards are systematically destroyed, causing direct and ongoing financial loss.

## Unprotected onBalanceChange lets anyone delete user fees
- Location: `contracts/FeeSplitter.sol` : `onBalanceChange`
- Mechanism: The `onlyManager` modifier on `onBalanceChange` is meaningless (see first finding), so the function is callable by anyone. It resets `userFeeOffset` to the current `cumulativeFeePerToken` without updating `unclaimedFees`. A malicious actor can call this for any (token, user) pair as long as that user has a token balance.
- Impact: An attacker can front‑run a legitimate `claimFees` or simply wipe the fees of any holder at any time, causing permanent loss of accrued rewards. This turns the fee distribution system into a griefing vector.

## Unrestricted fee parameter and factory changes
- Location: `contracts/Curves.sol` : `setFeeRedistributor`, `setMaxFeePercent`, `setProtocolFeePercent`, `setExternalFeePercent`, `setERC20Factory`
- Mechanism: These functions are protected only by the broken `onlyOwner`/`onlyManager` modifiers and are therefore publicly callable.
- Impact: An attacker can set `protocolFeeDestination` to their own address and collect all protocol fees, change the fee percentages to drain value, point `feeRedistributor` to a malicious contract (potentially enabling reentrancy), or replace the ERC20 factory with one that deploys backdoored tokens, allowing theft of all tokens that are withdrawn to ERC20 form.
