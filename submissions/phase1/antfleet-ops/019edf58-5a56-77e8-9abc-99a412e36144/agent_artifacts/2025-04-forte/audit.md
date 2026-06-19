# Audit: 2025-04-forte

Here are the genuine security vulnerabilities identified in the provided Solidity codebase:

## 1. Arithmetic Corruption in `add` and `sub` due to `exp()` Overflow
- **Location:** `src/Float128.sol` : `add`, `sub`
- **Mechanism:** When adding or subtracting two floats, the code aligns their exponents by scaling the mantissa of the smaller number. It calculates the exponent difference `adj` and then scales the mantissa using `exp(BASE, adj)` or `exp(BASE, sub(0, adj))`. If the exponent difference between the two operands is large (e.g., > 77), `exp(10, adj)` overflows the 256-bit EVM word. Because EVM `exp` computes modulo `2**256`, it returns a pseudo-random garbage number instead of a massive power of 10. The mantissa is then divided or multiplied by this garbage value, failing to zero out the insignificant operand and corrupting the resulting sum/difference.
- **Impact:** Any addition or subtraction of two numbers with an exponent difference greater than 77 (e.g., `10**100 + 10**-100`) yields an unpredictable, mathematically incorrect result. An attacker can intentionally trigger this to corrupt accounting, pricing, or logical checks in dependent contracts.

## 2. Exponent Underflow/Overflow Wrap-around in `mul` and `div`
- **Location:** `src/Float128.sol` : `mul`, `div`
- **Mechanism:** When multiplying or dividing, the new exponent is computed via 256-bit wrapping arithmetic (`rExp = aExp + bExp - ZERO_OFFSET` for `mul`). The valid range for the 14-bit signed exponent is `-8192` to `+8191`. If the mathematical result of the operation falls outside this range (e.g., `10**-8192 * 10**-8192` yields a true exponent of `-16384`), the 256-bit arithmetic silently wraps around the 14-bit boundary. The underflowed exponent `-16384` wraps to `+8191`. There are no bounds checks to clamp the result to zero or revert on out-of-bounds exponents.
- **Impact:** Extremely small or extremely large numbers can evaluate to magnitudes that are completely inverted (e.g. evaluating to `10**+8191` instead of underflowing to `0`). This can lead to catastrophic logical failures in any contract relying on this library for bounds or magnitude checks.

## 3. Incorrect Comparison Results due to Exponent Wrap-around in M-to-L Scaling
- **Location:** `src/Float128.sol` : `lt`, `le`, `gt`, `ge`
- **Mechanism:** To compare an M-size float (38 digits) with an L-size float (72 digits), the code scales the M-size number to L-size by multiplying its mantissa by `10**34` and decrementing its raw 14-bit exponent by 34 (`sub(aExp, shl(EXPONENT_BIT, DIGIT_DIFF_L_M))`). If the original true exponent of the M-size number is less than `-8158` (raw exponent < 34), this subtraction underflows the 14-bit unsigned integer space, wrapping around to a large positive exponent (e.g., `0 - 34` wraps to `16350`). The comparison logic then evaluates this wrapped positive exponent against the other operand, reaching entirely incorrect conclusions about the values.
- **Impact:** Comparisons between M and L floats with exponents near the minimum bound will return the exact opposite result. `lt`, `gt`, `le`, and `ge` will return `true` when they should return `false` and vice versa, breaking sorting, branching, and limit logic in dependent systems.
