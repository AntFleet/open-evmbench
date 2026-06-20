# Audit: 2024-01-curves

Here is the security audit of the provided Solidity codebase:

## Broken Access Control in Security Modifiers
- Location: `Security.sol` : `onlyOwner` and `onlyManager`
- Mechanism: The access control modifiers `onlyOwner` and `onlyManager` perform comparison operations (`msg.sender == owner;` and `managers[msg.sender] == true;`) without enclosing them within `require` statements or conditional `revert` blocks. These expressions evaluate to boolean values but are discarded, allowing transaction execution to proceed to the `_;` block unconditionally.
- Impact: Any caller can bypass access control checks completely to hijack ownership of the contracts (via `transferOwnership`), assign manager status, modify fee distributions, change vital factories, or claim/add arbitrary fees.

---

## Retroactive and Inflated Fee Claiming / Fee Theft via Token Transfers, Deposits, and Withdrawals
- Location: `Curves.sol` : `_transfer`, `withdraw`, `deposit`, `transferCurvesToken`, and `transferAllCurvesTokens`
- Mechanism: The contract allows token transfers, withdrawals (wrapping to ERC20), and deposits (unwrapping to Curves), but none of these operations notify the `FeeSplitter` contract to update historical fee state variables. Removing tokens via `withdraw` lowers the active `totalSupply` in `FeeSplitter`, inflating subsequent rewards (`cumulativeFeePerToken`) for remaining holders. When a user deposits ERC20s back or transfers curves tokens to another address, the recipient's balance changes without their `userFeeOffset` being updated. When they subsequently call `claimFees`, their newly acquired balance pays out retroactively against the historically inflated `cumulativeFeePerToken` rate.
- Impact: Attackers can double-claim fees, dilute actual holders, or utilize flash loans and transfer loops to siphon all the accumulated Ether rewards stored in the `FeeSplitter` contract.

---

## Missing Credit Record in FeeSplitter.onBalanceChange Wipes Out Pending Rewards
- Location: `FeeSplitter.sol` : `onBalanceChange`
- Mechanism: The `onBalanceChange` function is invoked by `Curves.sol` during buying and selling transactions. It immediately sets the user's `userFeeOffset` to the current `cumulativeFeePerToken` but fails to call `updateFeeCredit` beforehand to record their previously earned, unpaid earnings in the `unclaimedFees` mapping.
- Impact: Users completely lose all their pending accumulated fee rewards for a token whenever they make a subsequent purchase or sale of that same token.

---

## Denial of Service (DoS) via Unchecked Array Duplication in userTokens
- Location: `FeeSplitter.sol` : `onBalanceChange`
- Mechanism: Within `onBalanceChange`, the token subject is pushed to the `userTokens[account]` array whenever the user holds a balance. There is no deduplication check to ensure that the token is not already present in the user's array. Repeated interactions (buys/sells) with the same token continuously bloat the user's tracklist array.
- Impact: As the duplicated list size grows, retrieving rewards becomes excessively expensive. This causes view functions like `getUserTokensAndClaimable` and state-transition batches like `batchClaiming` to run out of gas and revert, permanently blocking the user's ability to claim their pending fees.

---

## State/Fee Out-Of-Sync Reentrancy in _transferFees
- Location: `Curves.sol` : `_transferFees`
- Mechanism: The `_transferFees` function transfers ETH payouts to the `curvesTokenSubject` and `referralFeeDestination` through low-level call execution before calling `feeRedistributor.addFees` and `feeRedistributor.onBalanceChange`. If either of these recipient addresses is a contract, they can hijack control flow via fallback or receive functions before the fee redistribution and offset states have finalized.
- Impact: Malicious token subjects or referral recipients can reenter the curves or fee redistributor contracts, executing actions (such as buying, selling, or claiming) while the internal balances and fee tracking variables are mismatching.
