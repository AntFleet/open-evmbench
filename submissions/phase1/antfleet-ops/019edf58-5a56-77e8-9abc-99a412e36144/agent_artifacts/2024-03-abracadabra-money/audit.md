# Audit: 2024-03-abracadabra-money

## MagicLpAggregator returns zero price due to missing return statement
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `_getReserves` / `latestAnswer`
- Mechanism: `_getReserves()` declares `returns (uint256, uint256)` but the function body only destructures `pair.getReserves()` into local variables and never returns them. In Solidity the unnamed return parameters default to zero, so `baseReserve` and `quoteReserve` are always `0` inside `latestAnswer()`. The final computation `minAnswer * (0 + 0) / pair.totalSupply()` always evaluates to `0`.
- Impact: Any consumer of this aggregator (e.g. a Cauldron using it as an oracle via `ProxyOracle`) will read a price of `0` for the LP token. This makes every borrower appear infinitely over-collateralised or, depending on the downstream math, instantly insolvent, enabling wrongful liquidations or preventing valid ones. The oracle is completely non-functional.

## FeeCollectable.setFeeParameters validates the old fee instead of the new fee
- Location: `src/mixins/FeeCollectable.sol` : `setFeeParameters`
- Mechanism: The guard `if (feeBips > BIPS)` checks the **current** storage value `feeBips` rather than the incoming `_feeBips`. When the current value is ≤ 10 000 (e.g. the initial `0`), the check always passes regardless of what `_feeBips` is supplied. The new `_feeBips` is then written to storage without any upper-bound validation.
- Impact: A fee operator can set `feeBips` above 10 000 (up to `type(uint16).max` = 65 535, i.e. 655 %). Any caller of `calculateFees` will then compute `feeAmount > amountIn`, causing `userAmount = amountIn - feeAmount` to either revert (Solidity 0.8 underflow) or, if set to exactly 10 000, return zero — permanently DoSing or fully taxing the affected flow.

## BlastOnboardingBoot._claimable values MIM and USDB 1:1 despite non-1:1 pool price
- Location: `src/blast/BlastOnboardingBoot.sol` : `_claimable`
- Mechanism: `_claimable` computes a user's pool-share allocation as `(userLockedMIM + userLockedUSDB) * totalPoolShares / (totals[MIM].locked + totals[USDB].locked)`, weighting MIM and USDB equally. However, the pool is created with `I = 0.998` (1 MIM = 0.998 USDB) and `totalPoolShares = min(quoteLocked / I, baseLocked)`. When the aggregate locked MIM and USDB are not in the exact I ratio, shares are minted on the `min` leg while the excess side's tokens sit unrepresented in the pool but are still counted in the `_claimable` denominator. Users who deposit the excess token are subsidised by (or subsidise) users who deposit the scarce token, depending on which side is oversupplied.
- Impact: Users who lock the relatively over-supplied token receive more pool shares than their economic contribution warrants, diluting users who locked the under-supplied token. This is a value-extraction issue rather than a fund-theft issue, but it results in an unfair distribution of the bootstrapped LP position.
