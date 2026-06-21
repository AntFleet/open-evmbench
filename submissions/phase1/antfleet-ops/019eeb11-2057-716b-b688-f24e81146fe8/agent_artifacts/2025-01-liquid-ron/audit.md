# Audit: 2025-01-liquid-ron
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Accrued operator fee is double-counted in `totalAssets()`
*(consensus, 6 of 6 reports)*
- Location: `src/LiquidRon.sol` : `totalAssets()` (interacting with `harvest`, `harvestAndDelegateRewards`, `fetchOperatorFee`)
- Mechanism: Before harvest, `getTotalRewards()` contributes pending rewards *net of fee* (`totalRewards - totalFees`). When `harvest()` runs, the proxy deposits the **full** claimed amount into the vault as WRON (`_depositRONTo(vault, claimedAmount)`), so `super.totalAssets()` (the vault's raw WRON balance) grows by the whole reward while `operatorFeeAmount += harvestedAmount * operatorFee / BIPS` records the operator's cut separately. `totalAssets()` returns `super.totalAssets() + getTotalStaked() + getTotalRewards()` and **never subtracts `operatorFeeAmount`**, so the WRON owed to the operator is booked simultaneously as an operator liability and as depositor-backing assets. For `harvestAndDelegateRewards()` it is worse: the gross reward is re-staked (counted 100% in `getTotalStaked()`) while the fee is later paid from idle depositor WRON in `fetchOperatorFee()`. Correct expression: `super.totalAssets() - operatorFeeAmount + getTotalStaked() + getTotalRewards()`.
- Impact: Price-per-share is overstated by `operatorFeeAmount / totalSupply` for the entire window between any harvest and the next `fetchOperatorFee()`. Any holder who exits during that window (via `withdraw`, `redeem`, or by being reserved at `finaliseRonRewardsForEpoch`, which prices with `previewRedeem`) extracts a pro-rata slice of the operator's fee — an MEV-friendly recurring leak. When `fetchOperatorFee()` finally pulls the fee, remaining holders absorb the shortfall; if idle WRON was already drained by exits, `fetchOperatorFee()` reverts and the operator cannot be paid. Value conservation is broken (true liabilities = `depositor_claims + operatorFeeAmount` exceed `totalAssets()`).

## Inverted `onlyOperator` modifier (`||` instead of `&&`)
*(consensus, 5 of 6 reports)*
- Location: `src/LiquidRon.sol` : `onlyOperator` modifier (just after the constructor)
- Mechanism: The check is `if (msg.sender != owner() || operator[msg.sender]) revert ErrInvalidOperator();`. The intended "owner OR operator" gate should revert only when `msg.sender != owner() && !operator[msg.sender]`. As written: a registered operator (`true || true`) always reverts, and the owner reverts too if ever flagged via `updateOperator(owner, true)` (`false || true`). The gate admits *only* the owner, and *only while the owner is not flagged as an operator*.
- Impact: The entire operator role is dead — `updateOperator` can never grant working access to `harvest`, `harvestAndDelegateRewards`, `delegateAmount`, `redelegateAmount`, `undelegateAmount`, or `finaliseRonRewardsForEpoch`. Worse, calling `updateOperator(owner, true)` permanently bricks every one of those functions: rewards can never be harvested, stake can never be undelegated, and `requestWithdrawal` queues can never be finalised — a permanent DoS / fund-lock. Fails closed (no privilege escalation), but a high-impact access-control logic defect.

## First-depositor / donation share-inflation attack (`_decimalsOffset() == 0`)
*(consensus, 2 of 6 reports)*
- Location: `src/LiquidRon.sol` : ERC4626 share math / `totalAssets()` / `getAssetsInVault()` — `_decimalsOffset()` not overridden (so 0); constructor mints nothing
- Mechanism: `totalAssets()` counts `IERC20(asset()).balanceOf(address(this))` directly, so anyone can `WRON.transfer(vault, X)` to inflate it with no share mint — the escrow indirection only protects the `deposit()`/`receive()` native flow, not arbitrary ERC20 transfers, and there is no reconciliation/sweep. With `_decimalsOffset() == 0` (virtual offset of 1) the classic inflation setup applies: attacker mints 1 wei → 1 share, donates a large WRON amount Y to push price-per-share to ~Y/2, after which a victim's deposit below `(totalAssets+1)/(totalSupply+1)` mints 0 shares via floored `previewDeposit`. The constructor doesn't seed; the deploy script seeds 10,000 RON only in a separate later broadcast.
- Impact: In the window between deployment and the seed (or on any chain where seeding is forgotten), an early depositor can grief/round-down-rob later small depositors, who forfeit deposits to the attacker's single share. Fix: override `_decimalsOffset()` to ~6 and/or seed shares in the constructor and track accounted balances instead of raw `balanceOf`.
- Reviewer disagreement: one report (O3) reproduced the setup but concluded that, after working the OZ virtual-share offset numbers, the simple attack is unprofitable for the attacker and declined to flag it.

## `maxWithdraw` / `maxRedeem` overstate the instantly withdrawable amount
*(consensus, 2 of 6 reports)*
- Location: `src/LiquidRon.sol` : inherited `maxWithdraw`/`maxRedeem` vs `withdraw`/`redeem` → `_withdraw` → `SafeERC20.safeTransfer`
- Mechanism: `totalAssets()` includes `getTotalStaked()` and `getTotalRewards()`, but the instant `withdraw`/`redeem` path can only pay out the vault's *idle* WRON (`_withdraw` does `safeTransfer(asset, …, assets)` then `_withdrawRONTo` unwraps). The inherited `maxWithdraw(owner)`/`maxRedeem(owner)` are computed from share balance against full `totalAssets()` with no cap on idle liquidity. When most assets are delegated to validators, the advertised maximum far exceeds the transferable balance.
- Impact: Violates the ERC-4626 invariant that `withdraw(maxWithdraw(owner), …)` and `redeem(maxRedeem(owner), …)` must succeed — they revert at the token transfer. Integrators/aggregators that trust these views fail, and users are misled about instant liquidity. The `requestWithdrawal`/epoch flow is the intended fallback, but the spec-level inconsistency breaks composability (availability/conformance defect, no direct theft).

## `redeem(uint256 _epoch)` emits the wrong epoch in `WithdrawalClaimed`
*(consensus, 2 of 6 reports)*
- Location: `src/LiquidRon.sol` : `redeem(uint256 _epoch)` (the withdrawal-epoch redeem)
- Mechanism: The function reads `uint256 epoch = withdrawalEpoch;` (the *current* epoch), performs all storage/payout logic against the caller-supplied `_epoch`, but emits `emit WithdrawalClaimed(msg.sender, epoch, shares, assets)` using the stale current `epoch`. `epoch` is otherwise unused.
- Impact: Off-chain accounting/indexers keyed on `WithdrawalClaimed.epoch` attribute claims to the wrong (currently-open) epoch, corrupting reconciliation of locked vs. claimed amounts and any fee/airdrop logic keyed on the event. No on-chain fund loss, but a genuine event-vs-state desync.
- Reviewer disagreement: one report (O3) stated that, since there are no narrowing downcasts in the codebase, the "truncation/event-desync class does not apply" — implicitly treating this class as a non-issue.

## `LiquidProxy.harvest()` credits the whole contract balance and `receive()` is open
*(consensus, 2 of 6 reports)*
- Location: `src/LiquidProxy.sol` : `harvest()` (`claimedAmount = address(this).balance`) together with the open `receive() external payable {}`
- Mechanism: `harvest()` computes the harvested reward as the proxy's entire native balance rather than the delta actually returned by `claimRewards`. Because `receive()` is intentionally left open, anyone can send RON directly to a proxy; the next `harvest()` sweeps that donation into the vault and charges `operatorFeeAmount += donation * operatorFee / BIPS` on funds that were never staking rewards.
- Impact: An external party can inflate `operatorFeeAmount` (an operator fee taken on non-reward principal) and distort reward/fee accounting at will. Combined with the `totalAssets()` double-count above, the donation is counted toward depositor assets while an extra fee is booked against the same pool, widening the insolvency gap. Standalone the attacker only loses money (low severity), but it is a genuine direct-balance vs accounted-balance discrepancy; harvest should be based on the delta returned by the staking contract.

## Minority findings

## `LiquidProxy.harvest()` re-claims the entire consensus-address array `length` times
*(minority, 1 of 6 reports)* *(conflicting reviews: 1 of 6 reports defended this code path)*
- Location: `src/LiquidProxy.sol` : `harvest()` (the `for` loop calling `IRoninValidator(roninStaking).claimRewards(_consensusAddrs)` with the whole array each iteration)
- Mechanism: The loop iterates `_consensusAddrs.length` times and on every iteration calls `claimRewards(_consensusAddrs)` over the full set, rather than claiming once (or claiming `_consensusAddrs[i]`). After the first iteration all rewards are already claimed/zeroed.
- Impact: If the real Ronin staking contract reverts when asked to claim already-claimed (zero-reward) validators — common for staking contracts — then `harvest` with two or more consensus addresses reverts on the second iteration, making reward harvesting unusable for any multi-validator batch (a DoS on protocol yield).
- Reviewer disagreement: one report (O1) identified the same redundant loop but classified it as gas waste / "not a fund bug" and deliberately excluded it under a no-gas-notes instruction.

## Epoch withdrawals underpay because finalized pool math reuses ERC4626 virtual offsets
*(minority, 1 of 6 reports)* *(conflicting reviews: 2 of 6 reports defended this code path)*
- Location: `src/LiquidRon.sol` : `redeem(uint256)` / `_convertToAssets` (and `finaliseRonRewardsForEpoch`)
- Mechanism: `finaliseRonRewardsForEpoch()` locks an exact withdrawal pool as `(lockedShares, assets)`, but epoch redemption converts each request with `_convertToAssets(shares, assetSupply, shareSupply)`, which adds the ERC4626 virtual assets/shares: `(_totalAssets + 1) / (_totalShares + 10 ** _decimalsOffset())`. Those offsets are appropriate for live share issuance, not for distributing a fixed finalized pool, so even a user owning all locked shares can receive less than the assets reserved for the epoch.
- Impact: Users redeeming through the delayed withdrawal flow (`requestWithdrawal` → `finaliseRonRewardsForEpoch` → `redeem(epoch)`) can be underpaid, with the remainder stranded in `Escrow`. Usually dust when `lockedShares` is large, but material for small locked-share epochs at high share price. No external attacker required.
- Reviewer disagreement: two reports (O2, O3) examined `_convertToAssets`/`previewRedeem` and defended it as sound, noting it rounds Floor "toward the protocol" with "no caller-favoring rounding" — i.e., they treated the same protocol-favoring rounding as correct rather than as a user-underpayment bug.

---

Finding count: 8 distinct findings identified across all six reports (operator-fee double-count, inverted `onlyOperator`, first-depositor inflation, `maxWithdraw`/`maxRedeem` overstatement, wrong-epoch event, `harvest` balance-sweep/open-`receive`, `harvest` re-claim loop, epoch-redemption virtual-offset underpayment); 8 findings emitted (6 consensus + 2 minority).

