# Audit: 2024-06-size

# Security Audit Report: Size Protocol

I reviewed the Size lending protocol, an order-book based P2P lending system backed by Aave v3 with a complex system of credit/debt positions, variable pool integration, and peer-to-peer matching.

---

## Missing `minTenor > 0` Check in `updateConfig`
- **Location**: `src/libraries/actions/UpdateConfig.sol` : `executeUpdateConfig`
- **Mechanism**: When updating `minTenor` via `updateConfig`, there is no check that the new value is non-zero or positive. The end-of-function re-validation calls `validateInitializeRiskConfigParams` which requires `minTenor != 0`, but the state is already written before the re-validation. More critically, the `minTenor` and `maxTenor` branches only check that the value is not too large relative to `swapFeeAPR`; they do not validate `minTenor < maxTenor` or `minTenor > 0` inline. If the admin sets `minTenor = 0`, all subsequent `validateTenor` checks pass for zero-tenor loans, and `createDebtAndCreditPositions` would create positions with `dueDate == block.timestamp` (immediately overdue), enabling instant liquidations or other manipulation.
- **Impact**: Admin can set `minTenor = 0`, allowing creation of instantly-overdue loans, or set `minTenor >= maxTenor` (caught only by end-of-function revert, but state is temporarily inconsistent). This is a governance footgun that could brick loan creation or enable MEV exploitation of zero-tenor positions.

---

## Validation/Execution Inconsistency in `Compensate` — Minimum Credit Not Checked in Validation
- **Location**: `src/libraries/actions/Compensate.sol` : `validateCompensate` / `executeCompensate`
- **Mechanism**: `validateCompensate` only checks `amountToCompensate == 0` but does not verify `amountToCompensate >= state.riskConfig.minimumCreditBorrowAToken`. In the `RESERVED_ID` branch, `executeCompensate` calls `createDebtAndCreditPositions` which internally calls `validateMinimumCreditOpening(creditPosition.credit)`. In the non-`RESERVED_ID` branch, `executeCompensate` calls `createCreditPosition` which also calls `validateMinimumCreditOpening`. The `amountToCompensate` can be as small as 1 wei (e.g., if `creditPositionWithDebtToRepay.credit` is very small, or if `params.amount` is small and gets capped), and validation passes, but execution reverts with `CREDIT_LOWER_THAN_MINIMUM_CREDIT_OPENING`.
- **Impact**: Users waste gas on validation that should have caught the error upfront. This is a denial-of-service / gas griefing vector for front-runners who can force users to pay for both validation and execution gas on transactions that are guaranteed to revert.

---

## Nested `multicall` Resets `isMulticall` Flag to False
- **Location**: `src/libraries/Multicall.sol` : `multicall`
- **Mechanism**: The `multicall` function sets `state.data.isMulticall = true` at the start and `false` at the end. If a user nests multicalls (e.g., `multicall([deposit(X), multicall([deposit(Y), repay(Z)])])`), the inner `multicall` sets `isMulticall = false` upon completion. Any subsequent operations in the outer `multicall` after the inner one will see `isMulticall == false`. This means the `borrowATokenCap` check in `executeDeposit` (which is skipped when `isMulticall == true`) will be enforced for later deposits, potentially causing unexpected reverts.
- **Impact**: Users who nest multicalls will experience unexpected reverts in later operations. This is a usability issue, not a direct fund-loss vector, but it could cause confusion and failed transactions. Additionally, an attacker could front-run a nested multicall to manipulate state between the inner and outer multicall boundaries.

---

## Missing WETH Zero-Address Validation in `initialize`
- **Location**: `src/libraries/actions/Initialize.sol` : `validateInitializeDataParams`
- **Mechanism**: The `validateInitializeDataParams` function checks for zero addresses on `underlyingCollateralToken`, `underlyingBorrowToken`, and `variablePool`, but does not check `d.weth` for address(0). If the protocol is initialized with `weth = address(0)`, the `deposit` function's WETH wrapping logic in `executeDeposit` will call `state.data.weth.deposit{value: amount}()` which will revert, making all ETH deposits permanently fail.
- **Impact**: The protocol could be deployed with a non-functional WETH integration, bricking all ETH-based deposits. This is a deployment-time error that would require a contract upgrade to fix.

---

## `compensate` Allows Same-Loan Self-Compensation Without Due-Date Mismatch Check
- **Location**: `src/libraries/actions/Compensate.sol` : `validateCompensate`
- **Mechanism**: The `compensate` function allows a borrower to use their own credit in the same loan (different `creditPositionId`) to repay their own debt. The due-date compatibility check `debtPositionToRepay.dueDate < debtPositionToCompensate.dueDate` passes when both are in the same loan (same due date). A borrower who is both borrower and lender in the same loan (possible via `sellCreditMarket` with `RESERVED_ID`) can compensate their own debt, effectively reducing their own debt and transferring credit to the original lender. The `createCreditPosition` call in `executeCompensate` then assigns the new credit to `creditPositionWithDebtToRepay.lender` (the original lender), which is correct. However, the fragmentation fee is only charged when `exiterCreditRemaining > 0`. In the same-loan case where the credit is fully consumed, no fee is charged, and the borrower effectively closes their position without paying the fragmentation fee that would apply to a cross-loan compensation.
- **Impact**: A borrower who holds credit in the same loan can avoid the fragmentation fee by self-compensating rather than using a cross-loan credit. This is a minor economic inconsistency, not a fund-loss vector.

---

## `updateConfig` Does Not Validate `variablePoolBorrowRateStaleRateInterval != 0`
- **Location**: `src/libraries/actions/UpdateConfig.sol` : `executeUpdateConfig`
- **Mechanism**: The end-of-function re-validation calls `validateInitializeOracleParams`, which only checks the price feed address and calls `getPrice()`. It does not validate `variablePoolBorrowRateStaleRateInterval`. If the admin sets this to 0, the `getAdjustedAPR` function in `YieldCurveLibrary` reverts with `STALE_RATE` for all yield curve lookups (because the condition `params.variablePoolBorrowRateStaleRateInterval == 0` is the first branch checked). This would brick all `buyCreditMarket`, `sellCreditMarket`, and `liquidateWithReplacement` operations that rely on yield curves with non-zero market rate multipliers.
- **Impact**: Admin can accidentally or maliciously set the stale rate interval to 0, permanently bricking all market-rate-dependent operations in the protocol. This is a governance footgun.

---

## `updateConfig` Does Not Validate `borrowATokenCap` Non-Zero or Consistency
- **Location**: `src/libraries/actions/UpdateConfig.sol` : `executeUpdateConfig`
- **Mechanism**: The `borrowATokenCap` update has no inline validation. If the admin sets it to 0, all single `deposit` operations (non-multicall) would revert with `BORROW_ATOKEN_CAP_EXCEEDED`. If the admin sets it below the current supply, the cap is effectively exceeded and all future single deposits fail. The end-of-function re-validation does not check the cap value.
- **Impact**: Admin can set `borrowATokenCap = 0`, preventing all single deposits. Users would need to use multicall (with a corresponding debt decrease) to deposit, which is a significant UX degradation and potential DoS.

---

## `PriceFeed` Update Not Validated for Liveness in `updateConfig`
- **Location**: `src/libraries/actions/UpdateConfig.sol` : `executeUpdateConfig`
- **Mechanism**: When updating the `priceFeed` key, the new price feed address is set directly. The end-of-function re-validation calls `validateInitializeOracleParams` which calls `getPrice()` once, confirming the feed works at that moment. However, if the new price feed is a contract that returns valid data during the update but later reverts (e.g., a malfunctioning or deprecated Chainlink feed), all collateral ratio calculations will revert, bricking liquidations, withdraws, and new loan creations.
- **Impact**: Admin can set a price feed that works at update time but fails later, permanently bricking risk-dependent operations. This is a governance risk inherent to oracle-dependent protocols.

---

## `sellCreditMarket` Uses `memory` Instead of `calldata` (Gas Inefficiency)
- **Location**: `src/Size.sol` : `sellCreditMarket`
- **Mechanism**: Unlike all other external functions which use `calldata`, `sellCreditMarket` declares its parameter as `memory`, causing an unnecessary calldata-to-memory copy.
- **Impact**: Gas inefficiency only; no security impact.

---

## Summary

The protocol is generally well-architected with proper access control, reentrancy protection (via the non-transferable token design), and validation. The findings above are primarily governance risks and validation/execution inconsistencies. The most actionable issues are the `minTenor` update validation gap and the `compensate` validation/execution inconsistency, both of which could cause user-facing problems.
