# Audit: 2024-01-curves

# Merged Security Audit Report

Two independent reviews (Reviewer A = Claude, Reviewer B = Codex) of the same contracts (`Security.sol`, `Curves.sol`, `FeeSplitter.sol`, `CurvesERC20.sol` + factory). Findings present in both reviews are consolidated first; single-reviewer findings follow.

---

## Consensus findings

## Broken access-control modifiers allow full privilege takeover
*(consensus)*
- Location: `Security.sol` : `onlyOwner`, `onlyManager` modifiers (lines ~10–30; also gate `setManager`, `transferOwnership`)
- Mechanism: Both modifiers contain a bare comparison expression that is evaluated and discarded instead of a `require`/`revert`:
  ```solidity
  modifier onlyOwner()   { msg.sender == owner; _; }            // no revert
  modifier onlyManager() { managers[msg.sender] == true; _; }   // no revert
  ```
  The statements `msg.sender == owner;` and `managers[msg.sender] == true;` have no side effects and never halt execution. The function body therefore runs unconditionally for any caller, and every privileged function in contracts inheriting `Security` is callable by anyone.
- Impact: Total loss of access control across the system. Any address can call `Security.transferOwnership(attacker)` and `Security.setManager(attacker, true)` to seize ownership/manager rights; `Curves.setProtocolFeePercent` / `setMaxFeePercent` / `setExternalFeePercent` to impose hostile fee configuration or redirect all protocol fees; and `Curves.setFeeRedistributor` / `setERC20Factory` to install malicious contracts (DoS / drain). This is a complete protocol compromise and the root enabler of several issues below.

## Anyone can repoint `FeeSplitter` to a malicious `Curves` contract and drain fees
*(consensus)*
- Location: `FeeSplitter.sol` : `setCurves(Curves curves_)` (line ~29), consumed by `claimFees` (lines ~66–73) and `batchClaiming` (lines ~82–98)
- Mechanism: `setCurves` carries no access control whatsoever (not even the broken `onlyOwner`), so anyone can repoint the `curves` reference. `FeeSplitter` trusts `curves.curvesTokenBalance` and `curves.curvesTokenSupply` when computing claimable holder fees (`balanceOf` / `totalSupply`). An attacker points `curves` at a contract that reports the attacker as holding all supply for any token.
- Impact: Any ETH held by `FeeSplitter` can be stolen by an arbitrary caller via `claimFees` / `batchClaiming` (and `addFees` distribution can be skewed). Preconditions are only that `FeeSplitter` has a positive ETH balance and the attacker can deploy a contract implementing the expected `curvesTokenBalance` / `curvesTokenSupply` interface.

## `onBalanceChange` resets the fee offset without banking accrued fees
*(consensus)*
- Location: `FeeSplitter.sol` : `onBalanceChange` (lines ~78–81), invoked from `Curves._transferFees` (lines ~189–221) after `Curves._buyCurvesToken` (lines ~234–253) has already increased the buyer's balance
- Mechanism: The correct accrual pattern credits `unclaimedFees` (via `updateFeeCredit`) *before* moving the offset. Instead, `onBalanceChange` does `data.userFeeOffset[account] = data.cumulativeFeePerToken;` directly, discarding the `(cumulativeFeePerToken - oldOffset) * balance / PRECISION` the holder had accrued since their last update. Because `_buyCurvesToken` increments the balance and *then* calls `onBalanceChange`, every subsequent trade overwrites the offset before realizing pending rewards.
- Impact: Two vectors from one root cause:
  1. **Accidental loss:** Any holder who buys/trades the same Curves token again before claiming permanently forfeits all holder fees accrued since their previous trade; the funds become stranded in `FeeSplitter`. This can also be induced in integrations that auto-compound or batch buys before fee claims.
  2. **Deliberate griefing:** Because `onlyManager` is a no-op (see *Broken access-control modifiers*), anyone can call `onBalanceChange(token, victim)` to reset a victim's offset to the current cumulative index, erasing their unclaimed entitlement before they claim.

---

## Additional findings (single-reviewer)

## Curves transfers do not sync `FeeSplitter` offsets → recipient claims historical holder fees never earned
*(Reviewer A only)*
- Location: `Curves.sol` : `_transfer` (callers `transferCurvesToken` / `transferAllCurvesTokens` / `withdraw` / `deposit`); interacts with `FeeSplitter.getClaimableFees` / `claimFees`
- Mechanism: `_transfer` updates `curvesTokenBalance` but never calls `feeRedistributor.onBalanceChange` for either party. Holder-fee accounting is offset-based: `getClaimableFees = (cumulativeFeePerToken - userFeeOffset[account]) * balance / PRECISION + unclaimedFees`. A fresh recipient has `userFeeOffset == 0` while `cumulativeFeePerToken` for an active subject is large, so on receiving tokens the recipient is credited with the *entire historical* fee-per-token times their balance — fees accrued before they ever held the token.
- Impact: An attacker buys tokens of a subject that has accrued holder fees, transfers them to a brand-new wallet B (offset 0), and `claimFees` pays `cumulativeFeePerToken * balance / PRECISION`, stealing fees owed to other holders. Repeating across fresh wallets drains the `FeeSplitter`'s pooled ETH, bleeding other subjects' fees too. No flash loan or special setup required beyond owning some tokens of an active subject.

## Sell-side protocol fee is never forwarded to `protocolFeeDestination`
*(Reviewer A only)*
- Location: `Curves.sol` : `_transferFees` (the `firstDestination` / `sellValue` branch)
- Mechanism: On a buy, `protocolFee` (or `protocolFee + referralFee`) is sent to `protocolFeeDestination`. On a sell (`isBuy == false`), `firstDestination` is `msg.sender` and receives `sellValue = price - protocolFee - subjectFee - referralFee - holderFee`. `subjectFee`, `referralFee`, and `holderFee` are paid out, but the `protocolFee` portion is never transferred to anyone — it is silently retained in the contract, and there is no admin function to recover raw ETH.
- Impact: The protocol never collects its fee on sells; that ETH is permanently locked in the bonding-curve contract. Asymmetric fee accounting versus the buy path and ongoing loss of protocol revenue.

## No reentrancy protection around external value transfers in `_transferFees`
*(Reviewer A only)*
- Location: `Curves.sol` : `_transferFees` (the `firstDestination.call` / `curvesTokenSubject.call` / `referralFeeDestination.call` block), reachable from `buyCurvesToken` / `sellCurvesToken`
- Mechanism: `_transferFees` performs raw full-gas `.call{value:...}` to up to three externally controlled addresses — `curvesTokenSubject` and `referralFeeDestination` (attacker-choosable) on buys, and `msg.sender` (the seller) on sells. These calls execute *before* the `feeRedistributor.onBalanceChange` / `addFees` bookkeeping completes, and there is no `nonReentrant` guard anywhere. Core curve state (`curvesTokenBalance`/`curvesTokenSupply`) is updated before the calls, but the `FeeSplitter` cross-contract state for the in-flight trade is still mid-update during the callback.
- Impact: A malicious `curvesTokenSubject`/referral contract (or seller) gains control mid-transaction and can re-enter `buy`/`sell`/`claimFees`/`deposit`/`withdraw` while holder-fee accounting is inconsistent. Combined with the offset bugs above, this widens the surface for manipulating fee credit. Should be closed with a reentrancy guard and strict CEI ordering.

## Unbounded duplicate growth of `userTokens` via `onBalanceChange`
*(Reviewer A only)*
- Location: `FeeSplitter.sol` : `onBalanceChange` (`userTokens[account].push(token)`)
- Mechanism: Every buy/sell pushes `token` into `userTokens[account]` whenever the post-trade balance is > 0, with no dedup check. A holder trading a subject N times accumulates N duplicate entries.
- Impact: `getUserTokens` / `getUserTokensAndClaimable` over-count and can eventually exceed the block gas limit (view DoS); off-chain integrations summing claimable across the list double-count. An attacker can deliberately bloat their own array — or, via the broken `onlyManager`, a victim's — to brick these views.

## Holder can front-run a subject's ERC20 naming via `withdraw`
*(Reviewer A only)*
- Location: `Curves.sol` : `withdraw` → `_deployERC20` (the auto-default-name branch)
- Mechanism: `withdraw` is callable by any holder and, if no external token exists yet, deploys the ERC20 — falling back to `DEFAULT_NAME` / `DEFAULT_SYMBOL` if the subject hasn't set a name. Deployment is not gated by `onlyTokenSubject`. Once deployed, the subject's later `setNameAndSymbol` and `mint` revert with `ERC20TokenAlreadyMinted`.
- Impact: A griefer holding a single token can permanently force a subject's tokenized ERC20 to carry the default `"Curves N"` / `"CURVESN"` metadata, denying the subject the ability to ever choose their own name/symbol.

---

### Note (not a finding)
Reviewer A flagged for awareness — not as a vulnerability — that `getPrice` computes `(supply - 1 + amount)` when `supply == 0`; under Solidity 0.8.7 the `supply - 1` underflows and reverts, so the very first purchase of a curve must be exactly `amount == 1`. This matches the original friend.tech formula and is a functional constraint rather than an exploitable flaw. Reviewer B did not raise it.

