# Audit: 2024-01-curves

Here are the critical security vulnerabilities in the provided codebase:

## Broken Access Control in `Security.sol`
- **Location:** `Security.sol` : `onlyOwner` and `onlyManager` modifiers
- **Mechanism:** The modifiers check the sender's access using `msg.sender == owner;` and `managers[msg.sender] == true;` respectively. However, these are merely boolean expressions and do not use `require()`, `revert()`, or any conditional logic to halt execution if the condition evaluates to `false`. 
- **Impact:** Any user can bypass access controls and call functions protected by `onlyOwner` and `onlyManager`. An attacker can manipulate core protocol parameters like changing the ERC20 factory, fee percentages, the fee redistributor, and assigning themselves as manager to steal funds from the `FeeSplitter`.

## User's Unclaimed Fees are Erased Upon Buying/Selling
- **Location:** `FeeSplitter.sol` : `onBalanceChange`
- **Mechanism:** When a user buys or sells points, `Curves` invokes `feeRedistributor.onBalanceChange` (from `_transferFees()`). In `FeeSplitter.sol`, this function simply resets `data.userFeeOffset[account] = data.cumulativeFeePerToken;` entirely bypassing the actual accumulation of fees the user is owed. It fails to call `updateFeeCredit(token, account)` prior to updating the offset.
- **Impact:** All of a user's pending, unclaimed fees for a token are permanently destroyed/lost under the token's respective `cumulativeFeePerToken` watermark whenever they buy or sell *any* amount of that token. 

## Protocol Drain via Unreported Token Transfers
- **Location:** `Curves.sol` : `_transfer`, `deposit`, and `withdraw`
- **Mechanism:** The protocol's `FeeSplitter` relies on `onBalanceChange` to update a user's fee offsets whenever their token balance changes, so they only earn fees distributed *after* they acquire their tokens. However, the `Curves` contract only informs the `FeeSplitter` during buys and sells. Standard token transfers (via `transferCurvesToken`), ERC20 wrappers (`withdraw`), and unwraps (`deposit`) bypass any notifications to the `FeeSplitter`.
- **Impact:** An attacker can transfer tokens to a fresh address (whose `userFeeOffset` defaults to `0`) and immediately call `claimFees()` in the `FeeSplitter`. Because the offset is zero and the user now has a balance, the contract will calculate rewards as if the user had held the tokens since inception, allowing the attacker to completely drain the `FeeSplitter` contract of its ETH.
