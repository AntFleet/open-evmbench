# Audit: 2024-01-curves

## Broken Access Control Modifiers
- Location: contracts/Security.sol : onlyOwner, onlyManager
- Mechanism: The access control modifiers use bare expression statements (`msg.sender == owner;` and `managers[msg.sender] == true;`) instead of enforcement statements like `require` or `if (...) revert`. In Solidity, these expressions simply evaluate to a boolean and discard the result without reverting the transaction or enforcing any condition.
- Impact: Any arbitrary address can completely bypass access controls and call owner/manager restricted functions. An attacker can take ownership of the protocol, change fee destinations to steal protocol fees, modify fee percentages, and manipulate the FeeSplitter contract.

## Destruction of Unclaimed User Fees
- Location: contracts/FeeSplitter.sol : onBalanceChange
- Mechanism: The function directly overwrites `data.userFeeOffset[account]` with the current `cumulativeFeePerToken` without first calculating and persisting the accumulated fees into `data.unclaimedFees[account]` (which is correctly done in `updateFeeCredit`). Combined with the broken `onlyManager` modifier, this function is publicly callable by anyone.
- Impact: Any attacker can repeatedly call `onBalanceChange` for any target user to reset their fee offset to the current cumulative value, permanently destroying their pending, unclaimed fee rewards before they have a chance to claim them.

## Unbounded Array Growth Leading to DoS
- Location: contracts/FeeSplitter.sol : onBalanceChange
- Mechanism: The function appends the `token` address to `userTokens[account]` every time it is called and the user's balance is > 0, without checking if the token already exists in the array (unlike `_addOwnedCurvesTokenSubject` in Curves.sol). Since this function is triggered on every buy/sell trade, the array grows indefinitely with duplicate entries.
- Impact: The unbounded array growth will eventually cause out-of-gas errors when the user attempts to claim fees via `batchClaiming` or view their data via `getUserTokensAndClaimable`, effectively locking them out of their fee rewards (Denial of Service).

## Precision Loss in Fee Distribution Accounting
- Location: contracts/FeeSplitter.sol : addFees
- Mechanism: The function calculates the fee per token as `(msg.value * PRECISION) / totalSupply_`. However, the `totalSupply()` getter already includes a multiplication by `PRECISION` (1e18). This causes the `PRECISION` multipliers to cancel out, effectively computing `msg.value / supply` and discarding any integer division remainder at the accumulation step.
- Impact: Fee dust (remainders from integer division) is permanently lost and locked in the FeeSplitter contract instead of being accurately distributed to token holders, leading to accounting inaccuracies and loss of yield over time.
