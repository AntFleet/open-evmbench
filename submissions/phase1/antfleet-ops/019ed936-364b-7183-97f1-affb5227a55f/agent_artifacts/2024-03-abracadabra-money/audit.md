# Audit: 2024-03-abracadabra-money

I have both reports in full, so I can merge them directly without further investigation. Let me work through the overlap.

**Overlap analysis:**
- Report A #1 ("LP oracle ignores reserves / returns 0") and Report B #3 ("LP oracle returns zero reserves") are the same bug — identical root cause (`_getReserves` never returns its local variables) and identical code path (`MagicLpAggregator._getReserves` → `latestAnswer`). → **Consensus**.
- A #2 (feed staleness/signedness) and A #3 (Router decimals underflow) appear only in A. → **Reviewer A only**.
- B #1 (cook solvency bypass) and B #2 (flash-loan fee skim) appear only in B. Note A explicitly examined both paths and judged them *not* vulnerable, but per instructions I preserve B's concrete claims rather than dropping or diluting them. → **Reviewer B only**.

---

# Merged Security Audit Report

## Consensus findings

## LP oracle never returns reserves and always prices the LP token at 0
*(consensus)*
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `_getReserves` (and its consumer `latestAnswer`)
- Mechanism: `_getReserves()` is declared `returns (uint256, uint256)` but its body only assigns the pair reserves to two *local* variables and never `return`s them:
  ```solidity
  function _getReserves() internal view virtual returns (uint256, uint256) {
      (uint256 baseReserve, uint256 quoteReserve) = pair.getReserves();
  }
  ```
  Because the nameless return tuple is never populated, the function silently returns `(0, 0)`. In `latestAnswer()` the destructured `baseReserve`/`quoteReserve` are therefore `0`, and the final expression `int256(minAnswer * (baseReserve + quoteReserve) / pair.totalSupply())` evaluates to `0` regardless of the real pool composition or the underlying base/quote price feeds. The oracle does not price the LP token at all — it returns a constant `0`.
- Impact: Any lending market / cauldron that wires this aggregator (through `ProxyOracle`/an `IOracle` adapter) as the price source for a MagicLP collateral receives a valuation of `0`. Depending on how the downstream wrapper converts the answer into an exchange rate, this is catastrophic in either direction: if the answer is inverted (`rate = k / price`) it reverts on division-by-zero, bricking `init`/`updateExchangeRate`/`borrow`/`liquidate`; if the `0` is consumed directly, the solvency RHS in `_isSolvent` collapses to `0`, so either every account is reported solvent and an attacker borrows MIM against ~zero collateral, or all collateral is valued at `0` and every borrower can be liquidated for free. The market's collateral pricing is completely non-functional and economically exploitable.

---

## Additional findings (single-reviewer)

## LP oracle has no staleness / signedness validation on the underlying feeds
*(Reviewer A only)*
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `latestAnswer` (the two underlying `latestAnswer()` reads)
- Mechanism: `latestAnswer()` calls `baseOracle.latestAnswer()` and `quoteOracle.latestAnswer()` and immediately casts each to `uint256` without checking `latestRoundData`'s `updatedAt`/`answeredInRound` for freshness and without checking that the answer is positive. A negative `int256` answer cast to `uint256` becomes an enormous number, and a stale (frozen) Chainlink feed is accepted as current. `latestRoundData()` here also fabricates `(0, latestAnswer(), 0, 0, 0)`, so any downstream consumer that *does* check `updatedAt` is told the round is from timestamp 0.
- Impact: A stale or mis-reported feed lets the LP collateral be priced against an outdated/garbage value, enabling borrowing against over-valued collateral or unjust liquidations. This compounds the consensus finding: even after the reserves bug is fixed, the price remains flash-stale/manipulable because no freshness or bounds check exists.

## Router pool creation reverts (panic) whenever base token has more decimals than quote
*(Reviewer A only)*
- Location: `src/mimswap/periphery/Router.sol` : `_validateDecimals` (used by `createPool` / `createPoolETH`)
- Mechanism:
  ```solidity
  if (quoteDecimals - baseDecimals > MAX_BASE_QUOTE_DECIMALS_DIFFERENCE) {
      revert ErrDecimalsDifferenceTooLarge();
  }
  ```
  `quoteDecimals` and `baseDecimals` are `uint8`. When `baseDecimals > quoteDecimals` (e.g. base = WETH/18, quote = USDC/6), `quoteDecimals - baseDecimals` underflows and the checked arithmetic reverts with a panic instead of evaluating the intended bound. The guard was meant to reject only *large positive* differences but instead hard-bricks an entire class of legitimate token-decimal orderings.
- Impact: Pool creation through the Router (`createPool`/`createPoolETH`) is permanently impossible for any pair where the base token's decimals exceed the quote token's. This is an availability/correctness defect in a configuration path: the only workaround is to bypass the Router and call the Factory directly (skipping the Router's seeding/validation logic), so it both blocks expected deployments and pushes users toward an unvalidated creation path.

## Cauldron `cook` can bypass the final solvency check
*(Reviewer B only)*
- Location: `src/cauldrons/CauldronV4.sol` : `cook`, `_additionalCookAction`
- Mechanism: `cook` tracks whether a final solvency check is required in `status.needsSolvencyCheck`, but any unrecognized/custom action falls through to `_additionalCookAction`. The base implementation returns the default empty `CookStatus`, and `cook` assigns `status = returnStatus`, clearing the pending solvency check. A caller can execute `ACTION_BORROW` or `ACTION_REMOVE_COLLATERAL`, then append an unhandled action such as `8`/`100`, causing the final `_isSolvent` check to be skipped. (Note: Reviewer A examined this path and judged the audited Abracadabra borrow/liquidation logic not vulnerable; this finding is reported by Reviewer B only and should be re-verified against the actual `cook`/`_additionalCookAction` control flow.)
- Impact: An attacker can borrow MIM or remove collateral through `cook` without remaining solvent. Preconditions are only that the cauldron has borrowable MIM/share liquidity and the borrow cap allows the amount.

## Flash-loan fees are not accounted and can be skimmed
*(Reviewer B only)*
- Location: `src/DegenBox.sol` : `flashLoan`, `batchFlashLoan`, `deposit`
- Mechanism: `flashLoan` and `batchFlashLoan` require repayment of `amount + fee`, but never add the fee to `totals[token].elastic`. The extra repaid tokens remain as unaccounted surplus. Because `deposit` intentionally allows anyone to skim surplus by using `from == address(this)`, any caller can mint shares against those flash-loan fees without providing tokens. In `batchFlashLoan`, repeated entries of the same token are also only checked against each individual fee instead of the aggregate fee, allowing borrowers to underpay fees for duplicate-token batches. (Note: Reviewer A examined DegenBox `deposit`/`withdraw`/`transfer` and judged the BoringMath accounting consistent; this finding is reported by Reviewer B only and should be re-verified against the fee-accounting path.)
- Impact: Any attacker can steal flash-loan fees after a loan completes by skimming the surplus into shares and withdrawing, and can underpay fees on duplicate-token batch flash loans.

