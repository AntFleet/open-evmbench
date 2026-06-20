# Audit: 2025-04-forte

## Overflowed decimal scaling corrupts `add`/`sub` for large exponent gaps
- Location: `src/Float128.sol` : `add()`, `sub()`
- Mechanism: Both functions align operands by computing `exp(BASE, adj)` inside assembly and then dividing or multiplying a mantissa by that value. This only works while `10**adj` fits in 256 bits. Once `adj` exceeds about 77, EVM `EXP` wraps modulo `2**256`; for `78 <= adj < 256` the code uses a garbage scale factor, and for `adj >= 256` the division path becomes `sdiv(x, 0) == 0`. Because exponent differences are allowed to be far larger than that, legitimate canonical inputs can reach these branches and produce numerically incorrect alignment before the final add/subtract.
- Impact: An attacker who can choose operands with widely separated exponents can force materially wrong arithmetic results instead of the mathematically correct sum/difference. Any protocol using these routines for balances, pricing, interest, or invariant math can mis-account value.

## `sqrt(0)` halts the entire caller with `STOP`
- Location: `src/Float128.sol` : `sqrt()`
- Mechanism: The zero case is handled with inline assembly `stop()` rather than returning packed zero. In an internal library function, `STOP` terminates the entire EVM call frame successfully and immediately, instead of just exiting the helper. That means `sqrt(0)` does not return a value and does not revert; it silently aborts all remaining logic in the calling function.
- Impact: If a reachable path can pass zero into `sqrt`, an attacker can short-circuit the rest of the caller’s execution while preserving any state changes already made earlier in the transaction. This can skip cleanup, settlement, transfers, or postcondition checks and still report success.

## `ln()` accepts non-positive inputs and returns finite values
- Location: `src/Ln.sol` : `ln()`
- Mechanism: `ln()` extracts only `mantissa`, `exponent`, and the L flag; it never checks `MANTISSA_SIGN_MASK` and never rejects zero. Negative values are therefore treated as their absolute value, and the special-case shortcut for `1` also fires for `-1` because the sign bit is ignored. Zero is passed into `ln_helper()` and run through the approximation logic, yielding a meaningless finite output instead of reverting or representing `-inf`.
- Impact: Any caller relying on logarithm domain safety can be fed invalid inputs such as `-1` or `0` and receive benign-looking finite numbers. That can break AMM/invariant math, risk checks, pricing, or any control path that assumes `ln(x)` is only evaluated for `x > 0`.

## Comparisons are based on encoding, not numeric equality
- Location: `src/Float128.sol` : `eq()`, `le()`, `ge()`
- Mechanism: `eq()` compares raw `packedFloat` words, not normalized numeric value. `le()` and `ge()` only treat values as equal when the raw words match; otherwise they fall through to strict mantissa/exponent comparisons. The format permits the same numeric value to exist in distinct valid encodings, most obviously as a 38-digit form and a 72-digit form. For such pairs, `eq()` is false, and `le()`/`ge()` can both be false even though the numbers are numerically equal.
- Impact: A user who can supply `packedFloat` values can bypass equality-based guards by re-encoding a forbidden value, and can also trigger inconsistent boundary behavior at exact thresholds. Protocol checks built on these helpers can therefore be bypassed or forced into impossible states with alternate encodings of the same quantity.

