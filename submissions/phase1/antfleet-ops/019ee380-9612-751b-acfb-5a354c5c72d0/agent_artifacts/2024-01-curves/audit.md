# Audit: 2024-01-curves

I'll report the genuine vulnerabilities I found, ordered by severity.

## Access-control modifiers are no-ops — entire privileged surface is unprotected
- Location: `contracts/Security.sol` : `onlyOwner` / `onlyManager`
- Mechanism: Both modifiers contain a bare comparison expression that is evaluated and then discarded — `msg.sender == owner;` and `managers[msg.sender] == true;`. There is no `require`/`if-revert`, so the boolean result is thrown away and execution always falls through to `_;`. Every function guarded by these modifiers is effectively public.
- Impact: Anyone can call `transferOwnership` to seize the contract, `setManager` to grant themselves manager rights, and — on `Curves` — `setProtocolFeePercent`, `setMaxFeePercent`, `setExternalFeePercent`, `setFeeRedistributor`, `setERC20Factory`. An attacker can repoint `protocolFeeDestination` to themselves and redirect all protocol fees, swap the factory/redistributor for malicious contracts, or raise fees arbitrarily. This is a total compromise of the protocol.

## `FeeSplitter.onBalanceChange` / `addFees` are reachable by anyone (compounded by broken `onlyManager`)
- Location: `contracts/FeeSplitter.sol` : `onBalanceChange`, `addFees`
- Mechanism: These are gated only by the broken `onlyManager` modifier above, so they are callable by any address. `onBalanceChange` writes `data.userFeeOffset[account] = data.cumulativeFeePerToken` for an arbitrary `account`.
- Impact: An attacker can call `onBalanceChange(token, victim)` to advance any holder's fee offset to the current cumulative value, zeroing their accrued-but-unclaimed `holdersFee` share (griefing/theft of pending rewards). They can also spam `userTokens[account].push(token)` to bloat that array and break `getUserTokensAndClaimable`.

## `FeeSplitter.setCurves` has no access control
- Location: `contracts/FeeSplitter.sol` : `setCurves`
- Mechanism: `setCurves(Curves curves_)` is `public` with no modifier at all. The `curves` reference is what `balanceOf`/`totalSupply` use to value every holder's stake.
- Impact: Anyone can repoint `curves` to an attacker-controlled contract that returns arbitrary `curvesTokenBalance`/`curvesTokenSupply` values, letting the attacker report a huge balance for themselves and then drain the accumulated `holdersFee` ETH via `claimFees`/`batchClaiming`.

## Token transfers (and sells) bypass FeeSplitter accounting → unearned/stolen holder fees
- Location: `contracts/Curves.sol` : `_transfer` (used by `transferCurvesToken`, `transferAllCurvesTokens`, `withdraw`, `deposit`) and `sellCurvesToken`
- Mechanism: Holder-fee accounting in `FeeSplitter` is lazy: claimable = `(cumulativeFeePerToken - userFeeOffset[account]) * balance`. The offset is only ever synced for a buyer, via the `onBalanceChange` call inside `_transferFees` on a buy. `_transfer` and `sellCurvesToken` change `curvesTokenBalance` without calling `onBalanceChange`, so the receiver's offset is never initialized. A recipient who never bought has `userFeeOffset == 0` while `cumulativeFeePerToken` is large.
- Impact: An attacker receives curves tokens via `transferCurvesToken` (or buys then moves them to a fresh account) and immediately calls `claimFees`, which computes fees as if they had held the tokens since `cumulativeFeePerToken` was zero. They drain ETH that belongs to legitimate long-term holders / the fee pool. Symmetrically, sellers lose their pending fees because their balance shrinks without their accrued amount being credited first.

## Protocol fee on sells is never paid out (stuck funds)
- Location: `contracts/Curves.sol` : `_transferFees`
- Mechanism: On a sell, `firstDestination = msg.sender` receives `sellValue = price - protocolFee - subjectFee - referralFee - holderFee`; `subjectFee`, `referralFee`, and `holderFee` are forwarded to their destinations, but the computed `protocolFee` is never transferred to `protocolFeeDestination`. The `buyValue` branch that would route it is only taken on buys.
- Impact: The protocol fee portion of every sell is silently withheld from the seller and left sitting in the contract with no path to withdraw it, permanently locking those funds. (The protocol never receives its sell-side revenue.)

---

The remaining items (the `getPrice` revert when the very first buy uses `amount > 1`, duplicate entries accumulating in `userTokens`) are correctness/DoS-of-self issues rather than attacker-exploitable vulnerabilities, so I'm not elevating them.

The single most important fix is the `Security` modifiers — every other contract inherits its access control from them, and as written they enforce nothing.

