# Audit: 2024-06-size

## Reentrancy via External Token/Pool Interactions
- Location: src/Size.sol : deposit (and symmetrically withdraw, repay, claim, liquidate, compensate, SellCreditMarket, BuyCreditMarket, and Deposit/Withdraw libraries)
- Mechanism: Multiple entrypoints perform external calls (`safeTransferFrom`/`forceApprove` on arbitrary `underlying*Token`, `variablePool.supply`/`withdraw`, and `collateralToken` transfers) before or between state updates and post-condition checks (e.g., CR validation, cap checks, `isMulticall` flag). No `ReentrancyGuard` or `nonReentrant` modifier is present on any function; the only protection is `whenNotPaused` and the internal `isMulticall` boolean.
- Impact: A malicious or callback-enabled ERC-20 (or a compromised Aave reserve) can re-enter the Size contract mid-operation, bypassing validation (e.g., opening-limit CR, minimum-credit, or cap checks), performing duplicate mints/burns, or manipulating multicall batch accounting.

## Missing Validation of Borrower on Market Orders When creditPositionId != RESERVED_ID
- Location: src/libraries/actions/BuyCreditMarket.sol : validateBuyCreditMarket
- Mechanism: When `creditPositionId != RESERVED_ID`, the function reads `creditPosition.lender` into the local `borrower` variable and later uses the existing loan's tenor, but never verifies that the `BorrowOffer` of that lender still exists or that the caller-supplied `params.borrower` (ignored) cannot be substituted; the offer-null check only runs on the resolved lender.
- Impact: An attacker can buy credit from a lender whose `BorrowOffer` has been cleared (null curve) by targeting an existing `CreditPosition`, allowing purchase of credit that should have been unavailable.

## Protocol Fee Can Be Set to 100% on Overdue/Underwater Liquidations
- Location: src/libraries/actions/Initialize.sol : validateInitializeFeeConfigParams (and executed via UpdateConfig)
- Mechanism: `overdueCollateralProtocolPercent` and `collateralProtocolPercent` are only checked `<= PERCENT`; nothing prevents an admin from setting either to exactly `PERCENT`, so that on a profitable liquidation the entire remainder after the liquidator reward is sent to `feeRecipient`.
- Impact: Admin (or a subsequently granted role) can redirect 100% of liquidation surplus to itself on any overdue or underwater position, draining borrower collateral that would otherwise be returned.

## Cap Bypass Still Possible via Multicall + Debt Reduction Ordering
- Location: src/libraries/Multicall.sol : multicall (combined with Deposit.executeDeposit and CapsLibrary.validateBorrowATokenIncreaseLteDebtTokenDecrease)
- Mechanism: `isMulticall` suppresses the hard `borrowATokenCap` check inside `deposit`; the post-multicall delta check only reverts when `borrowATokenSupplyIncrease > debtATokenSupplyDecrease`. An attacker can therefore sequence a large deposit followed by a compensating debt reduction (or repay) inside one multicall so the net delta passes while the intermediate supply temporarily exceeds the cap.
- Impact: Protocol can be forced to accept borrow aToken supply above the configured cap, violating the intended Aave liquidity limit and exposing the protocol to excess variable-pool exposure.
