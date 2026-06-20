# Audit: 2025-04-forte

 ## Natural logarithm accepts zero and negative inputs
- Location: `src/Ln.sol` : `ln`
- Mechanism: The function extracts only the mantissa and exponent bits of the input and never checks the sign bit or a zero mantissa. For a zero input the call flows into `ln_helper`, where `BASE_TO_THE_MAX_DIGITS_M_X_2 / mantissa` divides by zero and panics. For a negative input the sign bit is ignored, so `ln(-x)` returns the same value as `ln(x)` instead of reverting.
- Impact: A caller that passes a zero or negative packedFloat gets a panic revert or a mathematically wrong result. Downstream financial logic relying on `ln` can misprice options, yields, or collateral ratios when negative intermediate values are produced.

## Multiplication silently wraps out-of-range exponents
- Location: `src/Float128.sol` : `mul`
- Mechanism: The result exponent is computed in assembly as `sub(add(aExp, bExp), ZERO_OFFSET)`. The raw exponent values are 14-bit unsigned offsets, so adding two large positive encoded exponents (e.g., both representing `+8191`) produces a value far above the 14-bit signed range. Because the computation is in unchecked assembly, the excess bits wrap around and only the low 14 bits are written into the result.
- Impact: Multiplying two very large numbers yields a result whose encoded exponent wraps to a small or negative value, producing an arbitrarily wrong magnitude. A protocol using this library for position sizing or exchange rates could credit or charge the wrong amount.

## Division silently wraps out-of-range exponents
- Location: `src/Float128.sol` : `div`
- Mechanism: The L-operation path computes `rExp = (aExp + ZERO_OFFSET) - bExp` inside an `unchecked` block, and the subsequent assembly uses the wrapped value to encode the exponent. When the numerator has a very negative exponent and/or the denominator has a very positive exponent, the true result exponent falls outside the supported `[-8192, 8191]` range and the subtraction wraps.
- Impact: Division of extreme-magnitude values returns a packedFloat with an incorrect wrapped exponent. Any accounting derived from such a division (e.g., ratios, interest rates) will be wrong and can be manipulated by supplying operands at the format limits.

## Square root discards large-mantissa precision for small exponents
- Location: `src/Float128.sol` : `sqrt`
- Mechanism: The second (`else`) branch of `sqrt` scales an L-format input by only `BASE_TO_THE_DIFF_76_L` (or the plus-one variant) and performs Newton iteration on a 76-digit intermediate, then encodes the answer without the L flag. Inputs that use the 72-digit mantissa but whose exponent does not satisfy the first-branch condition are therefore computed with at most 38-digit precision, and the extra 34 digits are truncated.
- Impact: High-precision L inputs receive a low-precision square-root result. In precision-sensitive contracts this silently degrades accuracy and can cause downstream rounding errors, incorrect inequality checks, or unfair pricing.
