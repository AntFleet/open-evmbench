# Audit: 2024-01-curves

## Broken Access Control Modifiers (No Enforcement)
- Location: `Security.sol` : `onlyOwner`, `onlyManager`
- Mechanism: The modifiers evaluate a boolean expression (`msg.sender == owner;` and `managers[msg.sender] == true;`) as a bare statement with no `require`, `if-revert`, or assignment. The expression result is discarded, so the modifiers always pass regardless of the caller. Every `onlyOwner` and `onlyManager` function in the system is effectively public.
- Impact: Any attacker can call `transferOwnership`, `setManager`, `setFeeRedistributor`, `setProtocolFeePercent` (redirecting all protocol fees to themselves), `setERC20Factory`, `setMaxFeePercent`, `setExternalFeePercent`, and FeeSplitter's `onBalanceChange` / `addFees`. An attacker can instantly take full control of the protocol, redirect all fee streams, and manipulate the FeeSplitter's accounting to steal accumulated holder fees.

## FeeSplitter.setCurves Has No Access Control
- Location: `FeeSplitter.sol` : `setCurves`
- Mechanism: `setCurves` has no modifier at all—not even the broken ones from `Security`. Any caller can replace the `curves` reference with an arbitrary contract.
- Impact: An attacker can point `curves` to a malicious contract that returns arbitrary values for `curvesTokenBalance` and `curvesTokenSupply`, allowing them to manipulate `totalSupply` and `balanceOf` used in fee distribution. They can set total supply to 1 (for themselves) and then call `addFees` to inflate `cumulativeFeePerToken`, or claim fees they are not entitled to.

## FeeSplitter Accounting Never Updated on Transfers, Withdrawals, or Deposits
- Location: `Curves.sol` : `transferCurvesToken`, `transferAllCurvesTokens`, `_transfer`, `withdraw`, `deposit`
- Mechanism: `_transferFees` (called only during buy/sell) invokes `feeRedistributor.onBalanceChange` to update the FeeSplitter's dividend tracking. However, `transferCurvesToken`, `transferAllCurvesTokens`, `withdraw`, and `deposit` all call `_transfer` which moves balances but never calls `onBalanceChange` on the FeeSplitter. The FeeSplitter continues to use stale balance data.
- Impact: A user can transfer all their tokens to a fresh address, then claim fees from the FeeSplitter using the old address (which the FeeSplitter still believes has a balance), effectively claiming holder fees they no longer deserve. Conversely, the receiver cannot claim fees they are owed. This breaks the entire holder-fee distribution system and enables stealing fees from legitimate holders.

## onBalanceChange Skips updateFeeCredit, Destroying Pending Fees
- Location: `FeeSplitter.sol` : `onBalanceChange`
- Mechanism: `onBalanceChange` directly sets `data.userFeeOffset[account] = data.cumulativeFeePerToken` without first calling `updateFeeCredit` to credit the account's pending owed fees. Any fees that accumulated between the account's old offset and the current cumulative value are permanently lost for that account's existing balance.
- Impact: Every time a user buys tokens, their previously accumulated (but unclaimed) holder fees from their existing balance are wiped. Combined with the broken `onlyManager` modifier, an attacker can also call `onBalanceChange` on any victim at any time to destroy their pending fees—a pure griefing attack that steals dividend entitlements from all token holders.

## Protocol Fee Retained in Contract on Sells
- Location: `Curves.sol` : `_transferFees` (sell path)
- Mechanism: On sells, `firstDestination = msg.sender` and `sellValue = price - protocolFee - subjectFee - referralFee - holderFee`. The `protocolFee` is subtracted from the seller's proceeds but is never sent to `feesEconomics.protocolFeeDestination` (or anywhere else). It remains stuck in the contract with no withdrawal mechanism.
- Impact: The protocol destination never receives fees from sell activity, causing permanent revenue loss. The accumulated ETH is irrecoverable because there is no admin function to sweep the contract's residual balance.

## Referral Fee Lost on Sells When No Referral Is Set
- Location: `Curves.sol` : `_transferFees` (sell path)
- Mechanism: On the buy path, when `referralDefined` is false, the referral fee is merged into `buyValue` and sent to the protocol destination. On the sell path, no such merge occurs: `sellValue = price - protocolFee - subjectFee - referralFee - holderFee` always subtracts `referralFee`, but when `referralDefined` is false, the `referralFee` is never sent anywhere.
- Impact: For any token subject without a referral destination set, the referral fee portion of every sell is permanently trapped in the contract, representing a silent loss of funds.
