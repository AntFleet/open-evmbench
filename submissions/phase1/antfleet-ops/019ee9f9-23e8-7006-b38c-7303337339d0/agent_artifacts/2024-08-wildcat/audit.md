# Audit: 2024-08-wildcat

# Wildcat Protocol Security Audit Report

## Depositors can be permanently locked out of withdrawals
- Location: `src/access/AccessControlHooks.sol` : `onDeposit`, `_writeLenderStatus`, `onQueueWithdrawal`
- Mechanism: The hooks contract documents that lenders who have ever deposited “will always remain approved” for withdrawals, but `_writeLenderStatus` only sets `isKnownLenderOnMarket` when `hasValidCredential` is true at deposit time. A market can legally be configured with `depositRequiresAccess = false` (see `_onCreateMarket`, which explicitly separates “hook enabled” from “access required”). In that configuration, `onDeposit` allows deposits without a credential, yet `onQueueWithdrawal` unconditionally requires the lender to either already be a known lender or pass `_tryValidateAccess`. Depositors who entered without a credential are never marked as known lenders and can never queue a withdrawal.
- Impact: A borrower can deploy a market with `useOnDeposit = false` while withdrawal hooks remain active, accept unrestricted deposits, borrow against those deposits, and leave lenders with market tokens they cannot redeem. The same stuck-funds pattern affects transfer recipients when `transferRequiresAccess` is false: they receive tokens but are not marked known lenders and cannot withdraw.

## Transfer recipients can receive irrecoverable market tokens
- Location: `src/access/AccessControlHooks.sol` : `onTransfer`, `_writeLenderStatus`; `src/access/FixedTermLoanHooks.sol` : `onTransfer`, `_writeLenderStatus`
- Mechanism: On transfer, if the recipient is not already a known lender, the hooks only persist “known lender” status when `hasValidCredential` is true. If `transferRequiresAccess` is false, a recipient without a credential is allowed to receive tokens but is not recorded as a known lender. Subsequent `queueWithdrawal` calls still require known-lender status or a valid credential.
- Impact: Any sender can transfer market tokens to an address that lacks credentials, permanently trapping those tokens unless the recipient later obtains a credential through a provider. This enables griefing of counterparties and creates silently worthless token balances.

## `nukeFromOrbit` has no caller authorization despite sentinel-only documentation
- Location: `src/market/WildcatMarketConfig.sol` : `nukeFromOrbit`; `src/interfaces/IMarketEventsAndErrors.sol` : `BadLaunchCode`
- Mechanism: `IMarketEventsAndErrors` documents `BadLaunchCode` as the error for when a “non-sentinel” calls `nukeFromOrbit`, but the function never checks `msg.sender` against the sentinel. It only verifies that the target account is sanctioned, and then queues a full withdrawal via `_blockAccount`. Any address may call it.
- Impact: A third party can force-queue a sanctioned lender’s entire balance at a time of their choosing. Because queued withdrawals are reserved at 100% (not reserve-ratio), this can abruptly increase the borrower’s liquidity requirement and push an otherwise solvent market into delinquency, impairing the borrower’s ability to borrow or operate.

## Reserve-ratio solvency check uses stale ratio before applying a higher ratio
- Location: `src/market/WildcatMarketConfig.sol` : `setAnnualInterestAndReserveRatioBips`
- Mechanism: When the hooks contract returns a higher `reserveRatioBips` (for example after an APR reduction through `MarketConstraintHooks.onSetAnnualInterestAndReserveRatioBips`), the market checks `if (_reserveRatioBips > initialReserveRatioBips) { if (state.liquidityRequired() > totalAssets()) revert }`. At that point `state.reserveRatioBips` still holds the old, lower ratio, so `liquidityRequired()` understates obligations under the new ratio.
- Impact: A borrower can commit the market to a materially higher reserve requirement without the pre-update solvency check reflecting that new requirement. The market may become immediately delinquent after state is written, bypassing the intended “must be solvent at the new ratio before change” guard for voluntary ratio increases.

## Temporary elevated reserve ratio can be cancelled without ever maintaining it
- Location: `src/access/MarketConstraintHooks.sol` : `onSetAnnualInterestAndReserveRatioBips`
- Mechanism: During an active temporary-reserve period, if the borrower sets `annualInterestBips >= tmp.originalAnnualInterestBips`, `canCancel` is true and the hook deletes the temporary record and restores `tmp.originalReserveRatioBips` immediately—without requiring the borrower to have maintained the elevated reserves during the penalty window.
- Impact: A borrower can lower APR (triggering a higher temporary reserve ratio), then restore the original APR in a follow-up transaction and immediately drop back to the original, lower reserve ratio. This defeats the two-week elevated-collateral penalty that is meant to protect lenders when APR is reduced.

## Protocol fees can be collected while the market is delinquent
- Location: `src/market/WildcatMarket.sol` : `collectFees`; `src/libraries/MarketState.sol` : `withdrawableProtocolFees`
- Mechanism: `withdrawableProtocolFees` returns `min(totalAssets - normalizedUnclaimedWithdrawals, accruedProtocolFees)` and does not require the market to be solvent. `collectFees` has no `isDelinquent` guard and transfers those assets to `feeRecipient`.
- Impact: When a market is underwater, the fee recipient can still withdraw accrued protocol fees, removing assets that would otherwise be available to satisfy lender withdrawals and borrower collateral obligations. This worsens lender recovery during insolvency.

## Pull-provider credential reads use stale `returndatasize`
- Location: `src/access/AccessControlHooks.sol` : `_tryGetCredential`; `src/access/FixedTermLoanHooks.sol` : `_tryGetCredential`
- Mechanism: Credential pulls use `if and(gt(returndatasize(), 0x1f), staticcall(...))`. Depending on evaluation order, `returndatasize()` may be read before the `staticcall` executes, using returndata from an unrelated prior call in the same transaction rather than from the provider call being validated.
- Impact: In transactions that mix hook-gated market actions with other external calls, credential validation can produce false negatives (legitimate lenders denied) or, in edge cases with leftover returndata from a prior successful call combined with a failing provider call, accept stale success data. This weakens the access-control boundary on deposits, transfers, and withdrawals.

## `createEscrow` trusts any existing bytecode at the predicted address
- Location: `src/WildcatSanctionsSentinel.sol` : `createEscrow`
- Mechanism: `createEscrow` derives the CREATE2 address and, if `escrowContract.code.length != 0`, returns that address without verifying the deployed contract is a genuine `WildcatSanctionsEscrow` with the expected immutable parameters.
- Impact: If an attacker can place arbitrary bytecode at the predicted address before the sentinel deploys (for example via a separate deployment path that collides on address, or post-selfdestruct redeployment scenarios on chains where that remains practical), sanctioned-withdrawal funds sent by the market would be transferred to an attacker-controlled contract instead of a proper escrow. This breaks the sanctions-remediation fund-custody guarantee.

## Borrower-supplied `reserveRatioBips` is silently ignored
- Location: `src/access/MarketConstraintHooks.sol` : `onSetAnnualInterestAndReserveRatioBips`; `src/market/WildcatMarketConfig.sol` : `setAnnualInterestAndReserveRatioBips`
- Mechanism: The market passes both a new APR and a new reserve ratio to the hook, but `MarketConstraintHooks` initializes `newReserveRatioBips` from `intermediateState.reserveRatioBips`, ignoring the borrower’s input except when the temporary-ratio logic overrides it during APR reductions.
- Impact: A borrower cannot directly raise the reserve ratio through `setAnnualInterestAndReserveRatioBips` without going through the APR-reduction side channel. While primarily a liveness/configuration flaw, it can leave lenders exposed if they expect the named API to enforce a higher reserve ratio that never takes effect.

