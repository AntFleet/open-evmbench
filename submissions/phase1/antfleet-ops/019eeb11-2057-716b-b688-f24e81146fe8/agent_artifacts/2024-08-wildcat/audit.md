# Audit: 2024-08-wildcat
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Reconciliation summary

- Input reports: 6 (opus-4.8 ×3, gpt-5.5 ×3). One opus report (shot 2) raised **no** findings but explicitly defended several code paths.
- Distinct findings across all inputs (by code path + root cause): **7**
- Findings in this output: **7** (4 consensus, 3 minority) — no findings dropped.

---

## Consensus findings

## Deposits round scaled shares in the depositor's favor
*(consensus, 3 of 6 reports)*
- Location: `src/market/WildcatMarket.sol` : `_depositUpTo` (also `src/libraries/MarketState.sol` : `scaleAmount`, `src/libraries/MathUtils.sol` : `rayDiv`)
- Mechanism: `scaleAmount` converts assets to scaled shares with `rayDiv`, which rounds **half-up** instead of down. When `amount * RAY / scaleFactor` has a fractional part ≥ 0.5, the depositor is minted an extra scaled unit while transferring only the raw `amount`; the mint event also emits the requested `amount`, not the larger normalized value of the scaled balance minted. The inflated scaled amount is also passed to the deposit hooks, while the `maxTotalSupply` check caps only the raw `amount`.
- Impact: Once `scaleFactor` exceeds `RAY`, a lender can split deposits to repeatedly mint claims worth more than the assets supplied (e.g. at `scaleFactor ≥ 2e27`, a 1-wei deposit mints 1 scaled unit worth ≥ 2 wei). Creates unbacked market tokens, bypasses configured minimum-deposit and `maxTotalSupply` boundaries, and drains liquidity from other lenders when withdrawn.
- Reviewer disagreement: opus shots 2 and 3 verified the deposit/share-accounting paths as sound ("rounding directions are consistent"; the market "is not a price-per-share vault"), implicitly rejecting an over-mint.

## `transferFrom` can move more value than approved
*(consensus, 3 of 6 reports)*
- Location: `src/market/WildcatMarketToken.sol` : `transferFrom`, `_transfer` (also `src/libraries/MarketState.sol` : `scaleAmount`)
- Mechanism: Allowance is decremented in normalized `amount`, but `_transfer` converts that `amount` to scaled units with half-up `scaleAmount`. When the conversion rounds up, the scaled balance actually moved has a normalized value greater than both the allowance consumed and the emitted `Transfer` amount.
- Impact: A spender with a finite allowance can split transfers around rounding boundaries to move more economic value than the owner approved — up to roughly double near a rounding threshold, bounded by ~½ scaled unit per call, repeatable until the nominal allowance is exhausted. Precondition: a nontrivial accrued `scaleFactor` and a recipient that passes any enabled transfer hook.
- Reviewer disagreement: opus shot 2 verified the transfer-path downcasts and accounting as safe across "deposit, transfer, queue, and batch-burn."

## `nukeFromOrbit` (sanctions escrow) is bricked on fixed-term markets during the loan term
*(consensus, 2 of 6 reports)*
- Location: `src/market/WildcatMarketConfig.sol` : `nukeFromOrbit` → `src/market/WildcatMarket.sol` : `_blockAccount` → `src/market/WildcatMarketWithdrawals.sol` : `_queueWithdrawal` → `src/access/FixedTermLoanHooks.sol` : `onQueueWithdrawal`
- Mechanism: `nukeFromOrbit` forces a Chainalysis-sanctioned account's balance into escrow by queuing a full withdrawal through `_blockAccount` → `_queueWithdrawal` → `hooks.onQueueWithdrawal`. `FixedTermLoanHooks` carries `Bit_Enabled_QueueWithdrawal` as a **required** flag, so the hook always runs. It executes `if (market.fixedTermEndTime > block.timestamp) revert WithdrawBeforeTermEnd();` unconditionally and *before* any sanctions/access logic, so the internally-queued forced withdrawal reverts for the entire term.
- Impact: For up to `MaximumLoanTerm = 365 days`, the permissionless sanctions tool cannot process any sanctioned lender holding a balance; their tokens keep accruing interest and cannot be swept to per-account escrow, defeating the compliance guarantee. The only workaround requires the borrower to call `setFixedTermEndTime` to shrink the term — not an action available to the sentinel/operator.
- Reviewer disagreement: none of the reports that examined this path defended it (opus shot 2 reported "no vulnerabilities" overall but did not address the fixed-term gate on `nukeFromOrbit`).

## Open-deposit / gated-withdrawal desync strands uncredentialed lenders' own funds
*(consensus, 2 of 6 reports)*
- Location: `src/access/AccessControlHooks.sol` : `onDeposit` / `_writeLenderStatus` / `onQueueWithdrawal` (same pattern in `src/access/FixedTermLoanHooks.sol`)
- Mechanism: A market can be configured with `depositRequiresAccess == false` (open deposits) but the withdrawal hook enabled. `onDeposit` marks `isKnownLenderOnMarket` only when `hasValidCredential` is true (`_writeLenderStatus` gates the known-lender write on a valid credential), so a lender allowed to deposit *without* a credential is never recorded as a known lender. `onQueueWithdrawal` then requires `isKnownLenderOnMarket[lender] || _tryValidateAccess(...)`; with no credential and no known-lender flag, every voluntary withdrawal reverts `NotApprovedLender`.
- Impact: Funds deposited by credential-less lenders into such a market are irretrievable through the normal withdrawal path — a deposit-vs-withdrawal permission desync with no recovery function for the lender. Reachable only via a borrower-chosen configuration, so a footgun rather than an attacker exploit, but honest user funds can become permanently locked.
- Reviewer disagreement: opus shot 1 (which raised it) characterized it as a borrower-configuration "footgun" rather than an attacker-triggered exploit; opus shot 2 reported no vulnerabilities overall.

---

## Minority findings

## `nukeFromOrbit` is bricked on access-control markets for balances acquired without a credential
*(minority, 1 of 6 reports)*
- Location: `src/market/WildcatMarket.sol` : `_blockAccount` → `src/market/WildcatMarketWithdrawals.sol` : `_queueWithdrawal` → `src/access/AccessControlHooks.sol` : `onQueueWithdrawal`
- Mechanism: On an `AccessControlHooks` market that gates withdrawals, `_blockAccount` calls `_queueWithdrawal(..., msg.data.length)` so `extraCalldataBytes == 0` and no `hooksData` is forwarded; `onQueueWithdrawal` can therefore only pass via `isKnownLenderOnMarket` or an existing/pull credential. An account can hold a balance yet never be a known lender (it deposited where `depositRequiresAccess == false`, or received tokens via `onTransfer` where `transferRequiresAccess == false`, in both cases without a credential, since `_writeLenderStatus` sets known-lender only when `hasValidCredential` is true). If such an account is later sanctioned with no live credential, `onQueueWithdrawal` reverts `NotApprovedLender` and `nukeFromOrbit` reverts.
- Impact: A sanctioned holder of market tokens cannot be moved to escrow via the permissionless `nukeFromOrbit`; the borrower would have to first *grant the sanctioned address a credential* (unintuitive and counterproductive) for the nuke to succeed — sanctions enforcement is defeated. (Distinct from the consensus open-deposit finding: there the blocked path is the lender's own *voluntary* withdrawal; here the blocked path is the protocol's *involuntary* sanctions withdrawal.)
- Reviewer disagreement: none — only one report surfaced this sanctions-via-access-gate angle.

## Withdrawal batch payment can reserve more assets than actually available
*(minority, 1 of 6 reports)* *(conflicting reviews: 2 of 6 reports defended this code path)*
- Location: `src/market/WildcatMarketBase.sol` : `_applyWithdrawalBatchPayment`, `_applyWithdrawalBatchPaymentView`
- Mechanism: The payment path converts `availableLiquidity` to scaled units with `state.scaleAmount(...)` (half-up rounding), then computes `normalizedAmountPaid` from the rounded-up scaled amount. If available liquidity is ≥ half of one scaled unit but < a full scaled unit, the batch can burn 1 scaled unit and mark `floor(scaleFactor / RAY)` assets as paid even though fewer assets were actually available.
- Impact: A withdrawal batch can be recorded as paid with insufficient liquidity, inflating `normalizedUnclaimedWithdrawals` beyond the assets set aside; `executeWithdrawal` can then transfer the shortfall from other market funds, and the over-recorded payment can brick `closeMarket` paths that subtract it from available liquidity. Especially exploitable combined with the deposit-rounding issue.
- Reviewer disagreement: opus shot 2 stated withdrawal distribution rounds **down** (`mulDiv`), "leaving dust in the batch rather than over-paying," and that `normalizedUnclaimedWithdrawals` cannot underflow; opus shot 3 stated `_applyWithdrawalBatchPayment`'s rounding directions are consistent with the view and execute paths.

## Fee-on-transfer / rebasing assets are credited at the requested amount
*(minority, 1 of 6 reports)*
- Location: `src/market/WildcatMarket.sol` : `_depositUpTo`, `_repay`, `repay` (also `src/libraries/LibERC20.sol` : `safeTransferFrom`)
- Mechanism: The market mints deposit credit and records repayments from the caller-supplied `amount`, but `safeTransferFrom` only verifies the ERC20 call succeeded — it never checks the market's actual balance increase. For fee-on-transfer or rebasing tokens, the market can receive less than `amount` while accounting records the full value.
- Impact: For a market deployed against such an asset, depositors or repayers can create accounting claims larger than the assets actually received, leaving the market undercollateralized and shifting losses to other lenders/reserves. Precondition: a fee-on-transfer/rebasing asset is accepted (not blacklisted).
- Reviewer disagreement: none specifically — the opus reviews addressed only the absence of a price oracle and confirmed share price is not balance-derived; they did not examine fee-on-transfer asset handling.

