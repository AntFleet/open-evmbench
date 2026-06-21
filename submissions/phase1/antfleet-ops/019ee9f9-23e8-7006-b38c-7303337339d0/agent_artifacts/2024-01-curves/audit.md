# Audit: 2024-01-curves

Security audit of the provided Curves protocol contracts. Findings below are ordered by severity.

---

## Broken access control modifiers (no revert)

- **Location:** `Security.sol` : `onlyOwner`, `onlyManager`
- **Mechanism:** Both modifiers evaluate the authorization check but never revert on failure. `msg.sender == owner` and `managers[msg.sender] == true` are bare expressions whose results are discarded, so every gated function runs regardless of caller.
- **Impact:** Any address can call all `onlyOwner` and `onlyManager` functions across `Curves`, `FeeSplitter`, and `Security`, including `setProtocolFeePercent`, `setFeeRedistributor`, `setERC20Factory`, `setManager`, `transferOwnership`, `setMaxFeePercent`, `setExternalFeePercent`, `FeeSplitter.addFees`, and `FeeSplitter.onBalanceChange`. An attacker can redirect protocol fees, appoint themselves manager, change economics, grief fee accounting for arbitrary users, and take ownership of the protocol.

```solidity
modifier onlyOwner() {
    msg.sender == owner;  // missing: if (msg.sender != owner) revert ...
    _;
}
```

---

## Unprotected `setCurves` allows draining FeeSplitter

- **Location:** `FeeSplitter.sol` : `setCurves`
- **Mechanism:** `setCurves` has no access control. `balanceOf`, `totalSupply`, and all fee math read from the `curves` reference. An attacker can point `curves` at a malicious contract that returns inflated `curvesTokenBalance` values.
- **Impact:** After fees accumulate in `FeeSplitter`, an attacker sets `curves` to a mock, calls `claimFees` / `batchClaiming` with fabricated balances, and drains the contract’s entire ETH balance. Legitimate holders are left with nothing.

---

## Fee theft via `transferCurvesToken` (missing balance-change hook)

- **Location:** `Curves.sol` : `transferCurvesToken` / `_transfer`; `FeeSplitter.sol` : `onBalanceChange`, `claimFees`
- **Mechanism:** Holder-fee accounting uses per-user `userFeeOffset` in `FeeSplitter`. `onBalanceChange` is only called from `_transferFees` during buys/sells, not on peer-to-peer transfers. A recipient starts with `userFeeOffset == 0` while `cumulativeFeePerToken` may already be large.
- **Impact:** An attacker buys or receives a small amount of a curve, has someone transfer a large balance to them, then calls `claimFees`. `updateFeeCredit` computes `(cumulativeFeePerToken - 0) * balance`, crediting essentially all historical holder fees for those tokens to the attacker, stealing ETH from legitimate holders.

---

## Sellers lose accrued holder fees on sell

- **Location:** `Curves.sol` : `sellCurvesToken`; `FeeSplitter.sol` : `onBalanceChange`
- **Mechanism:** `sellCurvesToken` decrements `curvesTokenBalance` before `_transferFees`. `_transferFees` calls `onBalanceChange`, which sets `userFeeOffset = cumulativeFeePerToken` without first calling `updateFeeCredit` to snapshot accrued fees at the pre-sell balance. `balanceOf` already reflects the reduced balance.
- **Impact:** Sellers permanently lose holder fees accrued on the sold portion (and may lose pending fees on the remainder). Value that should go to sellers is stranded in `FeeSplitter` or diluted to other holders. This is a systematic accounting bug on every sell path.

---

## Unauthorized ERC20 deployment via `withdraw` (subject griefing)

- **Location:** `Curves.sol` : `withdraw`
- **Mechanism:** If no ERC20 exists yet, any token holder can trigger `_deployERC20` during `withdraw`, using default `"Curves"` / `"CURVES"` metadata. `externalCurvesTokens[curvesTokenSubject].token` is then set, blocking `setNameAndSymbol` and `mint` (`ERC20TokenAlreadyMinted`).
- **Impact:** A third party who holds even one curve token can front-run the subject’s `mint` / `setNameAndSymbol` and permanently lock in default ERC20 name/symbol, griefing the subject’s branding and launch plan.

---

## Excess ETH locked on overpayment (no refund)

- **Location:** `Curves.sol` : `_buyCurvesToken`
- **Mechanism:** The buy path checks `msg.value < price + totalFee` but never refunds when `msg.value > price + totalFee`. There is no `withdraw` or sweep on `Curves` for surplus ETH.
- **Impact:** Any user (or integrating contract) that overpays on `buyCurvesToken`, `buyCurvesTokenWithName`, or `buyCurvesTokenWhitelisted` loses the excess permanently. ETH accumulates in `Curves` with no recovery path.

---

## Holder fees stranded when `feeRedistributor` is zero

- **Location:** `Curves.sol` : `_transferFees`
- **Mechanism:** `holderFee` is only forwarded when `feesEconomics.holdersFeePercent > 0 && address(feeRedistributor) != address(0)`. If `holdersFeePercent > 0` but `feeRedistributor` is `address(0)`, that portion is deducted from the buyer/seller flow in fee math but never sent anywhere.
- **Impact:** With broken access control, an attacker can set `feeRedistributor` to zero while holder fees remain enabled, causing `holderFee` ETH to accumulate in `Curves` on every trade with no claim or sweep mechanism—permanent loss of value for holders and traders.

---

## Griefing fee accrual via unprivileged `onBalanceChange` (when combined with broken modifiers)

- **Location:** `FeeSplitter.sol` : `onBalanceChange`
- **Mechanism:** `onBalanceChange` resets `userFeeOffset` to the current `cumulativeFeePerToken` without crediting pending fees via `updateFeeCredit`. With broken `onlyManager`, anyone can call it for arbitrary `(token, account)` pairs.
- **Impact:** An attacker resets a victim’s fee offset right before the victim would claim, wiping uncheckpointed fee accrual and causing direct financial loss to holders.

---

## Integration failure: `Curves` is not authorized as FeeSplitter manager (latent)

- **Location:** `FeeSplitter.sol` : `addFees`, `onBalanceChange`; `Curves.sol` : `_transferFees`
- **Mechanism:** `_transferFees` calls `feeRedistributor.onBalanceChange` and `feeRedistributor.addFees`. Those require `onlyManager`. `FeeSplitter`’s constructor only makes `msg.sender` (deployer) a manager; `Curves` is never added as a manager, and `setCurves` does not grant manager rights.
- **Impact:** If `Security.sol` modifiers are fixed without also adding `Curves` as a manager on `FeeSplitter`, every trade with `holdersFeePercent > 0` reverts at `onBalanceChange` / `addFees`, causing a complete DoS on trading. This is a deployment/integration vulnerability that must be fixed alongside the modifier bug.

---

## `userTokens` unbounded duplicate entries (griefing / DoS)

- **Location:** `FeeSplitter.sol` : `onBalanceChange`
- **Mechanism:** Each call with `balanceOf(token, account) > 0` unconditionally `push`es `token` onto `userTokens[account]` with no duplicate check.
- **Impact:** Because `onBalanceChange` runs on every buy/sell, active traders accumulate duplicate entries. `batchClaiming` and `getUserTokensAndClaimable` iterate the full list; an attacker can inflate gas costs for victims (including via self-trading), making claims prohibitively expensive or blocking batch operations—a griefing/DoS vector on fee claims.

---

## Summary

The most critical issues are:

1. **Completely broken `onlyOwner` / `onlyManager`** — full protocol takeover.
2. **Unprotected `setCurves`** — drain of all `FeeSplitter` ETH.
3. **Broken fee accounting on transfers and sells** — theft and loss of holder fees.

These align with known issues from the Code4rena Curves (2024-01) contest. The codebase should not be deployed without fixing `Security.sol` modifiers, protecting `FeeSplitter.setCurves`, wiring `onBalanceChange` into transfers, checkpointing fees before balance decreases on sells, and addressing the ERC20 deployment race in `withdraw`.

