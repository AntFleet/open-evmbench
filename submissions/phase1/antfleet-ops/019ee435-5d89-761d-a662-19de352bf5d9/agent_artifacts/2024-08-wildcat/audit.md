# Audit: 2024-08-wildcat

## Rounding-up share conversion can over-mint claims
- Location: `src/market/WildcatMarket.sol` : `_depositUpTo`; `src/market/WildcatMarketToken.sol` : `_transfer` / `transferFrom`
- Mechanism: User-supplied normalized asset amounts are converted to scaled market shares with `state.scaleAmount(amount)`, which uses `rayDiv` rounding half-up. On deposit, the contract transfers exactly `amount` underlying but credits `scaledAmount` shares, whose normalized value can be greater than `amount` once `scaleFactor > RAY`. In `transferFrom`, allowance is decremented by the requested normalized `amount`, while the rounded-up scaled shares actually moved can represent more than that allowance.
- Impact: An attacker can split deposits or approved transfers into small amounts to extract rounding surplus from existing market liquidity, especially for low-decimal assets or high `scaleFactor` markets. This can also bypass intended approval and minimum-deposit amounts by moving/minting more value than the nominal amount supplied.

## Sanctions quarantine can be blocked by withdrawal hooks
- Location: `src/market/WildcatMarket.sol` : `_blockAccount`; `src/market/WildcatMarketWithdrawals.sol` : `_queueWithdrawal`; `src/access/FixedTermLoanHooks.sol` : `onQueueWithdrawal`
- Mechanism: `nukeFromOrbit` is intended to force a sanctioned account’s balance into the withdrawal/escrow path, but `_blockAccount` performs this through the normal `_queueWithdrawal` flow. `_queueWithdrawal` unconditionally calls `hooks.onQueueWithdrawal`, so hook restrictions meant for voluntary withdrawals also apply to sanctions enforcement. For example, `FixedTermLoanHooks.onQueueWithdrawal` reverts with `WithdrawBeforeTermEnd` before the fixed term ends.
- Impact: A sanctioned lender in a fixed-term market cannot be forcibly queued and escrowed until the term ends. Their balance remains in the market and continues to accrue debt/interest, preventing timely sanctions isolation and harming the borrower/market accounting.

## Fee-on-transfer deposits create unbacked market tokens
- Location: `src/market/WildcatMarket.sol` : `_depositUpTo`
- Mechanism: Deposits mint market tokens from the requested `amount` before/without verifying how many underlying tokens the market actually received. `asset.safeTransferFrom(msg.sender, address(this), amount)` only checks call success, not the balance delta. For fee-on-transfer, deflationary, or otherwise non-standard tokens, the market may receive less than `amount` while crediting the depositor for the full amount.
- Impact: If such an asset is permitted, a depositor can mint claims exceeding the assets delivered to the market and later withdraw against other liquidity, leaving losses to other lenders or the borrower.

