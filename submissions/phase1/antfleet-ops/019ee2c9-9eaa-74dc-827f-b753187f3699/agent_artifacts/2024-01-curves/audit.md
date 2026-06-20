# Audit: 2024-01-curves

Line references below refer to the pasted contracts.

## Broken access-control modifiers allow complete protocol takeover
- Location: `contracts/Security.sol` : `onlyOwner`, `onlyManager` (lines 8-16)
- Mechanism: Both modifiers evaluate a boolean expression and discard it instead of enforcing it. `msg.sender == owner;` and `managers[msg.sender] == true;` never revert, so every function guarded by `onlyOwner` or `onlyManager` is effectively public. That exposes `transferOwnership`, `setManager`, all fee setters in `Curves`, `setFeeRedistributor`, `setERC20Factory`, and manager-gated functions in `FeeSplitter`.
- Impact: Any attacker can seize ownership, grant themselves manager rights, redirect protocol fees to themselves, set arbitrary fee percentages, replace the ERC20 factory or fee redistributor with malicious contracts, and generally take full control of protocol funds and behavior.

## Anyone can repoint `FeeSplitter` to a fake `Curves` contract and drain holder fees
- Location: `contracts/FeeSplitter.sol` : `setCurves` (lines 35-37), consumed by `balanceOf`, `totalSupply`, `claimFees`, `batchClaiming`
- Mechanism: `setCurves` has no access control at all. `FeeSplitter` fully trusts the configured `curves` contract for `curvesTokenBalance()` and `curvesTokenSupply()` when computing fee entitlements. An attacker can point `curves` to a malicious contract that reports arbitrary balances for the attacker, then call `claimFees`/`batchClaiming` against subjects with accumulated fees.
- Impact: Any ETH held in `FeeSplitter` can be stolen by an arbitrary caller by fabricating a dominant holder balance and claiming fees that were meant for real token holders.

## Token transfers and bridge operations let recipients claim historical fees they never earned
- Location: `contracts/Curves.sol` : `_transfer` (lines 297-309), reached from `transferCurvesToken`, `transferAllCurvesTokens`, `withdraw`, `deposit`; interacts with `contracts/FeeSplitter.sol` : `getClaimableFees`
- Mechanism: Fee accrual in `FeeSplitter` is offset-based, so every balance change must preserve the sender’s accrued fees and initialize the recipient’s offset to the current cumulative index. `_transfer` only moves `curvesTokenBalance`; it never updates fee credits for `from` and never sets a fresh offset for `to`. A recipient with `userFeeOffset == 0` is therefore treated as if they had held the received balance since the beginning of fee accrual.
- Impact: A fresh wallet that receives internal Curves tokens, or receives them back through `deposit` after buying externalized ERC20s, can claim holder fees that accrued before it owned those tokens, draining `FeeSplitter` and depriving prior holders of rewards.

## `onBalanceChange` destroys accrued holder fees instead of banking them
- Location: `contracts/FeeSplitter.sol` : `onBalanceChange` (lines 96-100), called from `contracts/Curves.sol` : `_transferFees` (lines 230-232)
- Mechanism: `onBalanceChange` overwrites `userFeeOffset[account]` with `cumulativeFeePerToken` without first moving the already-earned amount into `unclaimedFees`. The correct accrual path exists in `updateFeeCredit`, but it is not used here. Because every buy and sell routes through `_transferFees`, a trader’s pending holder rewards are erased whenever they trade. The broken `onlyManager` modifier also lets third parties call this function directly against victims.
- Impact: Holders permanently lose unclaimed rewards on each buy/sell, and an attacker can also wipe another user’s pending fees on demand by calling `onBalanceChange` before the victim claims.

## Sell-side protocol fees are never paid out and become permanently stuck
- Location: `contracts/Curves.sol` : `_transferFees` (lines 213-227)
- Mechanism: On buys, `protocolFee` is sent to `protocolFeeDestination`. On sells, the first transfer sends `sellValue = price - protocolFee - subjectFee - referralFee - holderFee` to the seller, then subject/referral/holder fees are paid separately, but `protocolFee` is never transferred to any destination. There is also no withdrawal path for raw ETH left in `Curves`.
- Impact: Any seller can trigger permanent loss of the protocol’s sell-side fee revenue; those funds accumulate as trapped ETH in the bonding-curve contract.

## Any holder can irreversibly front-run ERC20 deployment metadata
- Location: `contracts/Curves.sol` : `withdraw` (lines 428-450)
- Mechanism: If no ERC20 exists yet, `withdraw` deploys it for the subject. This path is callable by any holder, not just the subject, and if the subject has not pre-set a name/symbol it force-falls back to `DEFAULT_NAME` / `DEFAULT_SYMBOL`. After deployment, `setNameAndSymbol` and `mint` can no longer be used because `externalCurvesTokens[curvesTokenSubject].token` is already set.
- Impact: A griefer who owns even one internal token can permanently force a subject’s ERC20 wrapper to launch under default metadata, denying the subject control over their token name/symbol forever.

