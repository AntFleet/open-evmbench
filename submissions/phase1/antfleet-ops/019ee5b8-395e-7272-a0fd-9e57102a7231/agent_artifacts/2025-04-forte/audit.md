# Audit: 2025-04-forte

## `sqrt(0)` Halts The Entire Caller With `STOP`
- Location: `src/Float128.sol` : `sqrt`
- Mechanism: The zero-input path executes inline assembly `stop()` instead of returning `packedFloat.wrap(0)` or reverting. Because this is an internal library function, `STOP` terminates the caller’s whole EVM frame successfully, not just the library function.
- Impact: Any contract that calls `sqrt` after making state changes can be forced to exit early with those prior changes committed and all later checks/effects skipped. An attacker-controlled zero input can bypass post-call accounting, invariant checks, or return-value handling.

## `ln` Accepts Zero And Negative Inputs
- Location: `src/Ln.sol` : `ln`
- Mechanism: `ln` extracts only the mantissa, exponent, and L flag. It never checks `MANTISSA_SIGN_MASK` and never rejects zero. Negative inputs are processed as if they were positive magnitudes; for example, a canonical `-1` has the same mantissa/exponent as `1`, so `ln(-1)` returns `0`.
- Impact: Protocols using `ln` for pricing, interest, bonding curves, or risk math can receive defined-looking outputs for undefined inputs. An attacker can feed negative or zero values to corrupt downstream accounting instead of triggering a revert.

## Exponent Underflow/Overflow Wraps Values Into Unrelated Magnitudes
- Location: `src/Float128.sol` : `toPackedFloat`, `add`, `sub`, `mul`, `div`
- Mechanism: Exponents are stored as a 14-bit biased field, but the code performs exponent arithmetic in unchecked assembly and then encodes with `shl(EXPONENT_BIT, rExp)` without validating that the result is still representable. Underflows/overflows therefore wrap modulo the exponent field. For example, adding two valid tiny M values with raw exponent `0` subtracts precision digits first, wrapping the intermediate exponent to a very large positive raw exponent.
- Impact: Valid boundary inputs can turn tiny values into astronomically large values, or huge/small multiplication and division results into unrelated magnitudes. Any contract relying on this library for balances, prices, collateral ratios, or limits can be made to misprice assets or bypass numeric thresholds.

## Comparisons Misorder Tiny M Values
- Location: `src/Float128.sol` : `lt`, `le`, `gt`, `ge`
- Mechanism: The comparison functions convert every M-sized mantissa to L-sized precision by multiplying the mantissa and subtracting `DIGIT_DIFF_L_M` from the exponent. If the M operand’s raw exponent is below `34`, that subtraction underflows and wraps to a very large exponent. A tiny positive M value near the minimum exponent can therefore compare greater than a larger positive value.
- Impact: Range checks such as minimum collateral, liquidation thresholds, price bounds, or ordering decisions can be inverted for attacker-supplied low-exponent values.

## Numeric Equality Is Not Canonicalized
- Location: `src/Float128.sol` : `eq`, `le`, `ge`
- Mechanism: `eq` compares the raw packed word instead of numeric value. The same number can be represented in both M and L form, for example `toPackedFloat(1, 0)` and `toPackedFloat(10**71, -71)` both represent `1` but have different packed encodings. `le` and `ge` first check raw equality, then use strict `<`/`>` logic, so numerically equal M/L values can make both `a <= b` and `a >= b` return false.
- Impact: Equality-based authorization, limit checks, order matching, or invariant checks can be bypassed or incorrectly fail when an attacker supplies an alternate valid encoding of the same numeric value.

