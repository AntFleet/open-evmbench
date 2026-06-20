# Audit: 2024-03-abracadabra-money

Below are the genuine security vulnerabilities I found.

## LP-token oracle always reports a price of zero
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `_getReserves` / `latestAnswer`
- Mechanism: `_getReserves()` is declared to return `(uint256, uint256)` but its body only assigns to two *local* variables and never executes a `return` statement:
  ```solidity
  function _getReserves() internal view virtual returns (uint256, uint256) {
      (uint256 baseReserve, uint256 quoteReserve) = pair.getReserves();
  }
  ```
  Solidity therefore returns the default `(0, 0)`. In `latestAnswer()` the result is consumed directly:
  ```solidity
  (uint256 baseReserve, uint256 quoteReserve) = _getReserves();   // (0,0)
  ...
  return int256(minAnswer * (baseReserve + quoteReserve) / pair.totalSupply());  // = 0
  ```
  so the aggregator unconditionally reports an LP price of `0`.
- Impact: Any Cauldron (or other consumer) that uses this aggregator as the collateral oracle values MagicLP collateral at zero. Every borrower with this collateral is instantly insolvent and can be liquidated to drain their collateral for effectively no MIM (or the protocol books bad debt), and no new borrowing against the collateral is possible. A core price feed returning a constant 0 is a critical valuation/accounting failure.

## Fee can be set above 100% (wrong variable validated)
- Location: `src/mixins/FeeCollectable.sol` : `setFeeParameters`
- Mechanism: The bound check is performed against the *existing* `feeBips` storage value instead of the new `_feeBips` argument that is actually being written:
  ```solidity
  function setFeeParameters(address _feeCollector, uint16 _feeBips) external onlyAllowedFeeOperator {
      if (feeBips > BIPS) {           // checks current value, not _feeBips
          revert ErrInvalidFeeBips();
      }
      ...
      feeBips = _feeBips;             // unchecked write
  }
  ```
  Because `feeBips` starts at 0 (and any previously-set valid value is `<= BIPS`), the guard never triggers, so a fee operator can write an arbitrary `_feeBips` up to `type(uint16).max` (655%).
- Impact: With `feeBips > BIPS` (10_000), `calculateFees` computes `feeAmount = amountIn * feeBips / BIPS > amountIn`, and `userAmount = amountIn - feeAmount` underflows and reverts under 0.8 checked math, bricking every fee-bearing path that calls `calculateFees`. More generally the fee is no longer bounded to 100%, so the validation that was meant to protect users is entirely ineffective.

I did not find additional exploitable issues in the core DegenBox/Cauldron/MagicLP/Router/staking paths beyond the two above; the flash-loan repayment checks, master-contract approval flow, and rebase accounting in those contracts appear sound.

