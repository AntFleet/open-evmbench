# Audit: 2024-08-wildcat

Both reports cover the same codebase but, after careful comparison, found **disjoint** sets of issues. No single finding appears in both: Report A's one finding (the fixed-term close/withdrawal lock) is absent from Report B, and Report B's five findings (rounding, fee-on-transfer, credential/known-lender stranding) are absent from Report A — in fact Report A explicitly examined the arithmetic/scaling paths Report B flags and judged them sound. The two reports do not share a root cause anywhere, so the Consensus section is empty by design rather than by omission.

A note on the one near-collision: Report A's finding and Report B's "Open deposits can create lenders that cannot withdraw" both end in `onQueueWithdrawal` reverting, but the root causes and code paths differ entirely — A is the `fixedTermEndTime` check ignoring `state.isClosed`; B is the credential / `isKnownLenderOnMarket` gate. They are kept as two separate single-reviewer findings, not merged.

---

# Merged Security Audit Report

## Consensus findings

*None.* The two reviews are non-overlapping — no vulnerability was independently reported by both A and B (same root cause and code path). All findings below are single-reviewer.

---

## Additional findings (single-reviewer)

## Closed fixed-term market permanently locks lender withdrawals
*(Reviewer A only)*
- Location: `src/access/FixedTermLoanHooks.sol` : `onQueueWithdrawal` — body `if (market.fixedTermEndTime > block.timestamp) revert WithdrawBeforeTermEnd();`; reachable via `WildcatMarket.sol` `closeMarket()` → `_queueWithdrawal` → `hooks.onQueueWithdrawal`, and via `nukeFromOrbit` → `_blockAccount` → `_queueWithdrawal`.
- Mechanism: The fixed-term withdrawal-gating hook enforces the loan term but intentionally discards the market state — its signature is `MarketState calldata /* state */`, so it never consults `state.isClosed`. The correct guard must also pass when the market is closed: `if (!state.isClosed && market.fixedTermEndTime > block.timestamp) revert WithdrawBeforeTermEnd();`. `closeMarket()` sets `state.isClosed = true`, drops APR to 0, raises the reserve ratio to 100%, and fully funds the market, but it only pays off batches that already exist — it does not create withdrawal requests for lenders still holding market tokens. Those lenders must then call `queueWithdrawal`/`queueFullWithdrawal`, which routes through `_queueWithdrawal` → `onQueueWithdrawal`; because the hook never checks `state.isClosed`, every such call reverts with `WithdrawBeforeTermEnd` whenever `block.timestamp < fixedTermEndTime`.
- Impact: A fixed-term market closed before its term ends becomes a fund trap. Although fully collateralized (close requires it) and earning 0%, any lender who had not already queued a withdrawal cannot exit principal until `fixedTermEndTime` — up to `MaximumLoanTerm = 365 days` later. Recovery depends on the borrower voluntarily calling `setFixedTermEndTime(market, now)`; an absent or malicious borrower leaves principal locked. The same root cause breaks the sanctions path: `nukeFromOrbit` → `_blockAccount` → `_queueWithdrawal` → `onQueueWithdrawal` reverts, so a sanctioned lender's balance on a closed-pre-term fixed-term market cannot be swept into the escrow contract, defeating the protocol's sanction-handling guarantee. No attacker funding is required — a normal early close triggers it.

## Rounded deposits can mint unbacked market tokens
*(Reviewer B only)*
- Location: `src/market/WildcatMarket.sol` : `_depositUpTo`; `src/libraries/MarketState.sol` : `scaleAmount`
- Mechanism: Deposits convert assets to scaled market tokens with `rayDiv`, which rounds half-up. Minting should round down in favor of existing lenders, but a depositor can choose amounts that round up to the next scaled unit while transferring fewer underlying assets than that scaled unit is worth at the current `scaleFactor`.
- Impact: After interest has increased `scaleFactor`, an attacker can repeatedly make small deposits that mint claims worth more than the assets paid, then withdraw those claims later, extracting value from existing market liquidity.

## Withdrawal batch payments can reserve more assets than available
*(Reviewer B only)*
- Location: `src/market/WildcatMarketBase.sol` : `_applyWithdrawalBatchPayment`
- Mechanism: The function converts `availableLiquidity` to scaled units using `state.scaleAmount`, which rounds half-up, then converts the burned scaled amount back to normalized assets with floor rounding. When `availableLiquidity` is just over half a scaled unit, the batch can burn one full scaled unit and mark more `normalizedAmountPaid` than the liquidity actually available.
- Impact: A withdrawal batch can be paid from assets that should remain reserved for other obligations, making withdrawals receive liquidity ahead of the reserve/fee constraints and pushing losses or delinquency onto remaining lenders.

## `transferFrom` can spend more value than the approved allowance
*(Reviewer B only)*
- Location: `src/market/WildcatMarketToken.sol` : `transferFrom`, `_transfer`
- Mechanism: `transferFrom` decreases allowance by the caller-supplied normalized `amount`, but `_transfer` debits the sender by `state.scaleAmount(amount)`, again rounded half-up. The scaled balance removed can be worth more than the allowance amount consumed.
- Impact: An approved spender can split transfers into rounding-favorable amounts and drain more normalized market-token value than the owner approved. Preconditions: `scaleFactor` has grown enough for asset-to-scaled rounding error to be non-negligible.

## Fee-on-transfer assets are credited at the requested amount
*(Reviewer B only)*
- Location: `src/market/WildcatMarket.sol` : `_depositUpTo`
- Mechanism: Deposits mint market tokens from the requested `amount` before/without checking the market's actual token balance delta after `asset.safeTransferFrom`. If the underlying asset charges transfer fees, rebases negatively, or otherwise transfers less than requested, the market still credits the depositor as if the full amount arrived.
- Impact: In any market using such an asset, a depositor can receive market-token claims exceeding assets received by the market, diluting or draining existing lenders. Preconditions: the market asset is a non-standard ERC20 that does not transfer the full requested amount.

## Open deposits can create lenders that cannot withdraw
*(Reviewer B only)*
- Location: `src/access/AccessControlHooks.sol` : `onDeposit`, `_writeLenderStatus`, `onQueueWithdrawal`; `src/access/FixedTermLoanHooks.sol` : same functions
- Mechanism: A successful deposit only marks `isKnownLenderOnMarket` when the lender has a valid credential. If a market is configured so deposits do not require credentials but queued withdrawals do, uncredentialed users can deposit successfully but are not recorded as known lenders, so later withdrawal queueing reverts unless they obtain a credential.
- Impact: A borrower can deploy a market configuration that accepts deposits from users who cannot later withdraw through the normal queue path. The same issue can strand recipients of transfers when transfers are allowed without credentials but withdrawals require them.

