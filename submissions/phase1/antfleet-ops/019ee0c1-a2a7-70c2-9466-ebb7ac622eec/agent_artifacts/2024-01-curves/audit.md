# Audit: 2024-01-curves

## Broken owner/manager access control
- Location: `contracts/Security.sol` : `onlyOwner`, `onlyManager`
- Mechanism: Both modifiers only evaluate a boolean expression (`msg.sender == owner;`, `managers[msg.sender] == true;`) and never revert when it is false. Every `onlyOwner` and `onlyManager` function is therefore publicly callable.
- Impact: Any attacker can change managers/owner, redirect protocol fees, set arbitrary fee percentages, replace the ERC20 factory, replace the fee redistributor, corrupt fee accounting through `FeeSplitter.onBalanceChange`, and generally take over all privileged protocol configuration.

## Unrestricted FeeSplitter source contract replacement
- Location: `contracts/FeeSplitter.sol` : `setCurves`
- Mechanism: `setCurves` is public and has no access control or one-time initialization guard. `claimFees` trusts `curves.curvesTokenBalance(token, account)` from whatever contract was last installed. An attacker can point `curves` to a malicious contract that reports an artificial balance for the attacker, then call `claimFees` for any token with accrued `cumulativeFeePerToken`.
- Impact: The attacker can drain ETH held by `FeeSplitter`, including fees owed to legitimate holders.

## Holder-fee claims can be replayed by transferring tokens
- Location: `contracts/Curves.sol` : `_transfer`, `transferCurvesToken`, `withdraw`, `deposit`; `contracts/FeeSplitter.sol` : `claimFees`, `getClaimableFees`
- Mechanism: Fee entitlement is tracked per address using `userFeeOffset`, but Curves balance transfers do not notify `FeeSplitter` for either the sender or recipient. A fresh recipient has `userFeeOffset == 0`, so `getClaimableFees` treats the recipient’s current balance as if it had held the tokens for the entire historical fee period. After claiming, the token can be transferred again to another fresh address and the same historical fees can be claimed again.
- Impact: An attacker holding a single Curves token can repeatedly transfer it through new addresses and drain the holder-fee pool, stealing fees owed to other holders.

## Wrapped supply can block sells when holder fees are enabled
- Location: `contracts/Curves.sol` : `sellCurvesToken`, `_transferFees`; `contracts/FeeSplitter.sol` : `totalSupply`, `addFees`
- Mechanism: `FeeSplitter.totalSupply` excludes Curves tokens locked inside the Curves contract as ERC20 backing. During a sell, Curves reduces the seller’s balance and total supply before calling `addFees`. If the sale leaves only wrapped/locked tokens, `FeeSplitter.totalSupply` returns zero and `addFees` reverts with `NoTokenHolders`.
- Impact: When `holdersFeePercent > 0`, an attacker can wrap enough tokens so a victim becomes the last unwrapped holder; the victim’s sell then always reverts, preventing them from exiting for ETH.

