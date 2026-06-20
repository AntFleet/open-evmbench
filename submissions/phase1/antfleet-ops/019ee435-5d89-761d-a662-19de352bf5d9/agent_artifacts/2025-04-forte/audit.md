# Audit: 2025-04-forte

## Large-branch `sqrt` returns results off by a factor of 10
- Location: `src/Float128.sol` : `sqrt`
- Mechanism: In the large-number branch, the code normalizes a 73-digit square-root mantissa by dividing `rMan` by `BASE` and incrementing `rExp` before halving `rExp`. The exponent halving is the square-root operation and should happen before the digit-width adjustment. With an even pre-adjustment exponent, `++rExp` is lost to integer division, so the mantissa is divided by 10 without the matching exponent increase.
- Impact: User-controlled large inputs can produce a square root that is 10x too small. Any protocol using this for collateral, pricing, risk, invariant, or accounting math can make materially wrong decisions.

## `sqrt(0)` silently halts the whole caller
- Location: `src/Float128.sol` : `sqrt`
- Mechanism: The zero-input path executes raw assembly `stop()` instead of returning packed zero. Because this is an internal library function, `STOP` terminates the current EVM call frame successfully, not just the helper function.
- Impact: A caller that reaches `sqrt(0)` exits early with success. State changes before the call remain, while all later accounting, checks, events, or transfers are skipped.

## `ln` accepts non-positive inputs
- Location: `src/Ln.sol` : `ln`
- Mechanism: `ln` extracts `mantissa`, `exponent`, and the large-mantissa flag, but never checks `MANTISSA_SIGN_MASK` or rejects zero. Negative values are processed as their absolute value, so `ln(-x)` returns approximately `ln(x)`. Zero reaches `ln_helper` and returns a meaningless finite packed float instead of reverting for an undefined logarithm.
- Impact: Attackers can feed `0` or negative values into callers that assume logarithms are only evaluated for `x > 0`, corrupting pricing, interest, risk, or invariant calculations with plausible-looking finite outputs.

## Equal numeric values can compare unequal
- Location: `src/Float128.sol` : `eq`, `le`, `ge`
- Mechanism: `eq` compares raw packed words instead of normalized numeric value. The same value can be represented with a 38-digit M mantissa or a 72-digit L mantissa, but the L flag and shifted exponent/mantissa make the raw words differ. `le` and `ge` only short-circuit on raw equality and then use strict `<`/`>` comparisons after normalization, so two numerically equal mixed-size encodings can make both `<=` and `>=` return false.
- Impact: Equality or boundary checks can be bypassed or incorrectly fail by supplying an alternate valid encoding of the same number.

## Low-exponent normalization underflows and turns tiny values into huge ones
- Location: `src/Float128.sol` : `add`, `sub`, `lt`, `le`, `gt`, `ge`
- Mechanism: Several paths subtract precision offsets directly from the encoded exponent field, such as `sub(aExp, shl(EXPONENT_BIT, MAX_DIGITS_M))` in `add`/`sub` and `sub(aExp, shl(EXPONENT_BIT, DIGIT_DIFF_L_M))` when promoting M operands to L. For valid values near the minimum stored exponent, this unsigned subtraction wraps the 14-bit exponent field to a near-maximum value. Later comparisons or result packing then treat a tiny number as if it had an enormous positive exponent.
- Impact: Arithmetic on valid low-exponent values can return massive corrupted results, and mixed M/L comparisons can invert ordering. Downstream solvency, threshold, pricing, or accounting checks can be bypassed when attackers control operands near the exponent floor.

## `toPackedFloat` discards most precision for 39-71 digit mantissas
- Location: `src/Float128.sol` : `toPackedFloat`
- Mechanism: When the mantissa is not already in the exact M or L normalized ranges, the function computes `mantissaMultiplier = digitsMantissa - MAX_DIGITS_M` and chooses L format only from `exponent + mantissaMultiplier > MAXIMUM_EXPONENT`. For mantissas with 39 to 71 digits and sufficiently small exponents, it chooses M format and divides by `10 ** (digitsMantissa - 38)`, truncating up to 33 significant digits even though L format could preserve them.
- Impact: A caller can create packed floats whose value is silently and severely rounded at construction. All later operations consume the corrupted value, leading to wrong balances, prices, rates, or invariant math.

