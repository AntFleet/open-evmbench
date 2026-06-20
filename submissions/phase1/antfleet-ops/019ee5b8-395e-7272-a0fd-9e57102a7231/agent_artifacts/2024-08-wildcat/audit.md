# Audit: 2024-08-wildcat

## Disabled templates remain usable through existing hook instances
- Location: `src/HooksFactory.sol` : `deployMarket` / `_deployMarket`
- Mechanism: `disableHooksTemplate` only prevents `_deployHooksInstance` from creating new hook instances. `deployMarket` accepts any already-created hooks instance, resolves its template, and deploys a market without checking `templateDetails.enabled`.
- Impact: A registered borrower who pre-deployed a hooks instance can keep launching new markets with a template after governance disables it, bypassing an emergency shutdown of a vulnerable or deprecated template.

## Fixed-term hook blocks closed-market exits and sanctions quarantine
- Location: `src/access/FixedTermLoanHooks.sol` : `onQueueWithdrawal`
- Mechanism: `onQueueWithdrawal` unconditionally reverts before `fixedTermEndTime`, ignoring the supplied `MarketState`. The same queue path is used for normal withdrawals, `closeMarket` aftermath, and `nukeFromOrbit` via `_blockAccount`.
- Impact: If a fixed-term market is closed before term end, lenders who have not already queued withdrawals cannot exit until the original term expires. A sanctioned lender also cannot be force-queued into escrow during the term, defeating the sanctions quarantine path.

## Rounded deposits can mint undercollateralized claims
- Location: `src/market/WildcatMarket.sol` : `_depositUpTo`; `src/libraries/MarketState.sol` : `scaleAmount`
- Mechanism: Deposits convert the requested asset amount to scaled shares with `rayDiv`, which rounds half-up. Minting should round down; instead a depositor can choose small amounts that round up to an extra scaled unit whose normalized value exceeds the assets transferred.
- Impact: After `scaleFactor` grows, an attacker can repeatedly deposit rounding-favorable amounts, mint more market-token value than paid in underlying assets, and withdraw value from existing liquidity.

## Withdrawal batch payment can reserve more assets than available
- Location: `src/market/WildcatMarketBase.sol` : `_applyWithdrawalBatchPayment`
- Mechanism: The function converts `availableLiquidity` to scaled units using the same half-up `scaleAmount`. If liquidity is just over half a scaled unit, the batch can burn one full scaled unit, then record `normalizedAmountPaid` for that full unit, which can exceed the liquidity actually available for the batch.
- Impact: Withdrawal batches can consume assets that should remain reserved for fees, prior withdrawals, or required liquidity, shifting losses/delinquency to remaining lenders.

## `transferFrom` can move more value than approved
- Location: `src/market/WildcatMarketToken.sol` : `transferFrom` / `_transfer`
- Mechanism: `transferFrom` decrements allowance by the caller-supplied normalized `amount`, but `_transfer` converts that amount to scaled shares with half-up rounding. The scaled shares debited from `from` can normalize to more than the allowance amount consumed.
- Impact: An approved spender can split transfers into rounding-favorable calls and drain more market-token value than the owner approved.

## Fee-on-transfer assets are credited at face value
- Location: `src/market/WildcatMarket.sol` : `_depositUpTo`
- Mechanism: Deposit accounting mints shares from the requested `amount` and never checks the market’s actual token balance delta after `asset.safeTransferFrom`. Deflationary, fee-on-transfer, or otherwise non-exact ERC20s can deliver less than `amount`.
- Impact: A depositor can receive market-token claims exceeding assets actually received by the market, diluting existing lenders and creating insolvency.

## Open deposits can strand users behind withdrawal access control
- Location: `src/access/AccessControlHooks.sol` : `onDeposit` / `_writeLenderStatus` / `onQueueWithdrawal`; `src/access/FixedTermLoanHooks.sol` : same path
- Mechanism: If a market enables withdrawal access checks but leaves deposit or transfer access open, uncredentialed users can receive or deposit market tokens. They are only marked `isKnownLenderOnMarket` when they have a valid credential, so later `onQueueWithdrawal` rejects them unless they obtain one.
- Impact: A borrower can configure a market that accepts funds from users who cannot later queue withdrawals through the normal path, trapping their position until external credentials are granted.

