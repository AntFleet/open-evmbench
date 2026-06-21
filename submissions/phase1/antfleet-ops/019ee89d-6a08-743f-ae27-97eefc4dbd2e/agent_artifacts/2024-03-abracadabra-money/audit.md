# Audit: 2024-03-abracadabra-money

## Broken MagicLP price feed — oracle always returns zero
- Location: src/oracles/aggregators/MagicLpAggregator.sol : `_getReserves` / `latestAnswer`
- Mechanism: `_getReserves()` is declared with an *unnamed* return tuple `returns (uint256, uint256)`, but its body assigns `pair.getReserves()` into two freshly-declared local variables `(uint256 baseReserve, uint256 quoteReserve)` and has no `return` statement. The named-return slots are therefore never written, so the function returns the default `(0, 0)`. `latestAnswer()` then does `(uint256 baseReserve, uint256 quoteReserve) = _getReserves();` (both 0) and computes `int256(minAnswer * (baseReserve + quoteReserve) / pair.totalSupply())`, which is always `0`. The aggregator (used to price MagicLP collateral) thus reports a price of 0 unconditionally.
- Impact: Any Cauldron whose collateral oracle is backed by this aggregator gets `exchangeRate == 0`, making every borrower trivially "solvent" so collateral can be borrowed against with no backing (drain), or — if the oracle wrapper inverts the price and divides by zero — bricking `updateExchangeRate`/liquidations and freezing the market with unrecoverable bad debt.

## Fee bound check validates the wrong variable in FeeCollectable
- Location: src/mixins/FeeCollectable.sol : `setFeeParameters`
- Mechanism: The guard reads `if (feeBips > BIPS) revert ErrInvalidFeeBips();` — it checks the *current* storage value `feeBips` instead of the incoming parameter `_feeBips`. Consequently `_feeBips` is written to storage completely unvalidated, so a fee operator can set `feeBips` to any `uint16` above `BIPS` (i.e. >100%). Once set, `calculateFees` computes `feeAmount = amountIn * feeBips / BIPS > amountIn`, and `userAmount = amountIn - feeAmount` underflows and reverts; additionally the setter itself is now permanently bricked because every future call reverts on the (now >BIPS) stored `feeBips`.
- Impact: A fee operator can push the fee above 100%, which reverts all fee-charging swaps that use `calculateFees` and irrecoverably locks the fee configuration, causing a denial of service on any integrating contract.

## Decimals validation underflows and blocks valid pool creation
- Location: src/mimswap/periphery/Router.sol : `_validateDecimals`
- Mechanism: The spread check `if (quoteDecimals - baseDecimals > MAX_BASE_QUOTE_DECIMALS_DIFFERENCE)` subtracts two `uint8` values in checked arithmetic. When the base token has more decimals than the quote token (e.g. base = 18-decimal token, quote = 6-decimal token), `quoteDecimals - baseDecimals` underflows and reverts before the comparison is ever evaluated. The check is only one-directional, so any pair where base decimals exceed quote decimals cannot be created through `createPool` / `createPoolETH`.
- Impact: Creation of otherwise-valid MagicLP pools is permanently reverted for an entire class of token pairs (high-decimal base / low-decimal quote), a denial of service on the router's pool-creation path.

