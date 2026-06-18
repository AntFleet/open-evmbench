# Audit: 2025-04-forte

Below is the merged report. I treated the two reviewers' `ln` domain-validation issues as consensus (Report B bundles negative+zero into one finding; Report A splits them into two — I kept A's two-way split to preserve the per-case mechanism detail, since both reports cover both cases). The `toPackedFloat`/result-packing exponent-wrap issue is consensus. The remaining three findings each appear in only one report and are distinct root causes (A's promotion-underflow comparison *inversion* is not the same bug as B's equal-M/L-compare-unequal, and B's `sqrt(0)` stop() is absent from A).

---

# Merged Security Audit Report — Float128 / Ln math library

Scope note (from Report A, uncontested by B): this is a pure, stateless math library — no storage, external calls, tokens, or access-controlled mutators. All genuine findings fall under arithmetic/type-safety and input validation.

## Consensus findings

## `Ln.ln` silently accepts negative inputs and returns `ln(|x|)` instead of reverting
*(consensus)*
- Location: `src/Ln.sol` : `ln(packedFloat)` (decode block `mantissa := and(input, MANTISSA_MASK)`; no `MANTISSA_SIGN_MASK` test), flowing into `ln_helper` (around lines 55–145).
- Mechanism: `ln` extracts the mantissa with `and(input, MANTISSA_MASK)`, which strips bit 240 (the mantissa sign). The sign is never read or checked anywhere in `ln`/`ln_helper`, so a negative `packedFloat` is processed exactly as its absolute value and `ln(-x)` evaluates to `ln(x)`. The `ln(1)`/`+1` early-return shortcut additionally makes `ln(-1)` return zero. Unlike `Float128.sqrt`, which reverts on a negative operand (`"float128: squareroot of negative"`), `ln` has no equivalent domain guard. Negative `packedFloat`s are routinely produced by `sub`/`mul`/`add`, so a negative argument is easily reachable.
- Impact: `ln(-x)` returns a plausible, finite, but mathematically wrong value with no revert. Any consumer deriving a value from `ln` of an intermediate that can go negative (interest/vol/pricing/bonding curves, invariant checks) gets a silently incorrect number rather than a fail-safe revert, with no on-chain signal that the domain was violated. Precondition: an attacker can influence the `packedFloat` passed to `ln` or to a caller that uses it.

## `Ln.ln` does not guard `input == 0` and returns garbage instead of reverting
*(consensus)*
- Location: `src/Ln.sol` : `ln(packedFloat)` → `ln_helper(mantissa=0, exp=-8192, inputL=false)` (around lines 55–145).
- Mechanism: For `input == 0` (the canonical zero `packedFloat`), `mantissa = 0` and `exponent = -8192`. The early-return only matches `ln(1)`. In `ln_helper`, `positiveExp = 8192`, so neither `MAX_DIGITS_M(38) > 8192` nor `MAX_DIGITS_L(72) > 8192` holds → the `else` branch runs. That branch never divides by `mantissa` (the reciprocal division that would revert lives only in the `input ≥ 1` branch), so `calculateQ1/2/3(0)` proceed, `z_int = 10**76 - 0 = 10**76`, and the routine encodes a meaningless `packedFloat`. `ln(0)` is mathematically −∞.
- Impact: `ln(0)` returns a bogus finite value with no revert, indistinguishable from a legitimate result. Combined with the negative-input issue above, both critical domain boundaries of `ln` (x ≤ 0) fail open, feeding silently corrupt values into any pricing/interest/invariant logic.

## Exponent field wraps during result packing without range validation
*(consensus)*
- Location: `src/Float128.sol` : `toPackedFloat(int mantissa, int exponent)` (final `or(..., shl(EXPONENT_BIT, add(exponent, ZERO_OFFSET)))`, around lines 1025–1085), plus the result-packing steps in `div` (around lines 610–665), `mul`, `add`, `sub`, and `sqrt`.
- Mechanism: Exponents are adjusted in assembly / `unchecked` arithmetic and then packed with `shl(EXPONENT_BIT, rExp)` (`EXPONENT_BIT = 242`) without validating that the encoded exponent lies within the 14-bit offset range `[0, 16383]` (documented actual range `[-8192, 8191]`). Out-of-range values are silently truncated modulo the exponent field — e.g. `exponent + ZERO_OFFSET == 16384` shifts to `2^256 ≡ 0`, encoding exponent 0; a quotient whose true exponent is below the minimum wraps into an ordinary positive exponent. Because the write is OR-combined with the mantissa, the result is mis-scaled rather than reverting. Normalization paths assume in-range inputs and never re-clamp.
- Impact: Extreme-but-representable operands (or an internal path / caller driving `exponent` out of range) produce unrelated finite results instead of reverting or saturating. As the primary constructor used throughout `Float128` and `Ln`, this lets attacker-influenced math inputs corrupt price, collateral, or threshold calculations with no failure signal.

## Additional findings (single-reviewer)

## M→L promotion underflows the 14-bit exponent field, inverting mixed-size comparisons and corrupting mixed-size arithmetic
*(Reviewer A only)*
- Location: `src/Float128.sol` : the promotion snippet `aMan := mul(aMan, BASE_TO_THE_DIGIT_DIFF); aExp := sub(aExp, shl(EXPONENT_BIT, DIGIT_DIFF_L_M))` (and the `b` variant) in `lt`, `le`, `gt`, `ge`, `add`, `sub`, plus the equivalent shift-less form in `mul`/`div`.
- Mechanism: When one operand is M-sized and the other L-sized, the M operand is up-converted by multiplying its mantissa by `10^34` and subtracting `DIGIT_DIFF_L_M (34)` from its stored exponent (bits 242–255, a 14-bit field, stored value = actualExp + 8192). The subtraction is plain unsigned `sub` with no floor check. If the M operand's stored exponent is `< 34` (actualExp `< -8158`, normally constructible down to stored exp 0), the field wraps to `(storedExp - 34) mod 2^14` — a near-maximum value — so the operand appears to have an enormous exponent. This is *not* uniform: only the M operand is shifted, so relative ordering against the untouched L operand is inverted. (For two same-sized operands the shift is uniform and order is preserved — explicitly ruled out as a false positive — so this only bites mixed M/L pairings.)
- Impact: In `lt/le/gt/ge`, comparing such a tiny M number against an ordinary L number returns the opposite boolean (e.g. `lt(tiny_M, normal_L)` → `false`, `gt(tiny_M, normal_L)` → `true`); a protocol using these as price/threshold/solvency checks reads the relationship backwards. The same underflowed exponent feeds result encoding in `add`/`sub`/`mul`/`div` at near-floor exponents, producing a corrupted huge-exponent result. Precondition: an operand within 34 of the exponent floor (−8192) combined with a larger-sized operand — exotic but reachable from valid encodings and from chains of divisions of tiny quantities.

## `sqrt(0)` halts the entire caller successfully via raw `stop()`
*(Reviewer B only)*
- Location: `src/Float128.sol` : `sqrt` (around lines 670–690).
- Mechanism: The zero-input path executes raw EVM `stop()` inside inline assembly instead of returning `packedFloat.wrap(0)`. Because `sqrt` is an internal library function, this opcode terminates the entire current call frame successfully, not just the library function.
- Impact: Any exposed state-changing caller that reaches `sqrt(userInput)` with `userInput == 0` can be forced to exit early while reporting success. State changes made before the call persist, while post-`sqrt` accounting, checks, events, or transfers are silently skipped — a griefing/partial-execution vector.

## Equivalent M/L encodings compare unequal at boundaries (`eq` raw-word compare; `le`/`ge` strict)
*(Reviewer B only)*
- Location: `src/Float128.sol` : `le`, `ge`, `eq` (around lines 830–1015).
- Mechanism: `eq` compares the raw packed word instead of numeric value. `le` and `ge` only return early on raw equality; after normalizing M-sized operands to L-sized, the equal-mantissa/equal-exponent case still uses strict `<`/`>` checks, so numerically equal M and L encodings return false for both `<=` and `>=`. (Distinct from the promotion-underflow inversion above: here the values are genuinely equal but report unequal.)
- Impact: Boundary checks can fail or be bypassed when values come from mixed-precision paths (e.g. `div`/`toPackedFloat` producing M values and `divL` producing L values for the same number). A caller using negated comparisons or equality-sensitive liquidation/limit logic can make exact-threshold values behave as non-equal.

