# Audit: 2025-04-forte

**Incorrect 2's complement sign handling in subtraction path**

- Location: `src/Float128.sol` : `add` (and identically in `sub`)
- Mechanism: When `isSubtraction` is true the code extracts unsigned mantissas, scales them, then does `if and(b, MANTISSA_SIGN_MASK) { bMan := sub(0, bMan) }` (and likewise for `a`). The subsequent `addition := add(aMan, bMan)` therefore receives values that have already had their original signs applied via the 2's-complement negation, but the `isSubtraction` flag later decides a completely separate normalization branch that assumes the opposite sign semantics.
- Impact: An attacker-supplied pair of opposite-sign values that trigger the subtraction normalization path can produce a result whose sign bit and magnitude are inverted relative to the mathematical `a+b`, allowing an attacker to force incorrect accounting results in any contract that relies on the library for balances or prices.

**Missing overflow check on exponent addition in multiplication**

- Location: `src/Float128.sol` : `mul`
- Mechanism: `rExp := sub(add(shr(EXPONENT_BIT, aExp), shr(EXPONENT_BIT, bExp)), ZERO_OFFSET)` is performed with plain `add` on the raw 14-bit exponent fields; the subsequent normalization only clamps against `MAXIMUM_EXPONENT` after the 512-bit division, never before the `shl(EXPONENT_BIT, rExp)` that writes the final packed value.
- Impact: Two large positive exponents cause the intermediate sum to exceed 14 bits; the stored exponent wraps, producing a value whose magnitude is off by many orders of magnitude and that can be used to underflow or inflate any dependent calculation (e.g., collateral ratios).

**Division-by-zero check only examines mantissa bits**

- Location: `src/Float128.sol` : `div` (the internal overload)
- Mechanism: The only zero-denominator guard is `if eq(and(b, MANTISSA_MASK), 0) { revert ... }`; a packedFloat whose mantissa is zero but whose exponent or L-flag bits are nonzero still passes the test and proceeds to `Uint512.div512x256` (or the plain `div`) with a zero divisor.
- Impact: Attacker can craft a denominator that is mathematically zero yet evades the check, causing the EVM `div`/`div512x256` to return zero or garbage; any contract using the result for a price or rate can be driven to an incorrect state.

**Unchecked arithmetic on exponent in `ln_helper`**

- Location: `src/Ln.sol` : `ln_helper`
- Mechanism: `unchecked { rExp = (aExp + ZERO_OFFSET) - bExp; }` (and similar additions/subtractions of `DIGIT_DIFF_*` constants) occurs after the `Loperation` decision that may have already added `DIGIT_DIFF_L_M` etc.; no test is performed against the 14-bit exponent field width.
- Impact: Inputs near the maximum representable exponent cause the resulting packedFloat to contain a wrapped (or negative) exponent, so subsequent calls to `ln` or any arithmetic that consumes the result compute the wrong natural logarithm and can be exploited for incorrect yield or fee calculations.

**Taylor-series loop in `intermediateTermAddition` uses unbounded iteration count derived from input**

- Location: `src/Ln.sol` : `intermediateTermAddition`
- Mechanism: `terms = 15` is a constant, but the loop multiplies `z_to_j = z_to_j.mul(z)` and divides by `j` without any guard that the intermediate `packedFloat` values stay within the representable exponent range; the preceding `ln_helper` path that reaches this code already permits arbitrarily large `m10`.
- Impact: Large-magnitude inputs produce intermediate values whose exponents overflow the packed representation, silently corrupting the final logarithm returned to the caller.
