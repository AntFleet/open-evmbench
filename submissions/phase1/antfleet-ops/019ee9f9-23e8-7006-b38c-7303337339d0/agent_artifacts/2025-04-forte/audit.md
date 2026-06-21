# Audit: 2025-04-forte

# Security Audit: Float128 & Ln Libraries

Analysis is based on the provided `Float128.sol`, `Ln.sol`, and `Types.sol`. These are pure math libraries (no access control or reentrancy surface), but several logic flaws can corrupt accounting, halt transactions, or cause reverts when a protocol uses them on user-controlled inputs.

---

## sqrt(0) terminates the entire transaction via `stop()`

- **Location:** `Float128.sol` : `sqrt`
- **Mechanism:** For a zero input, the assembly block executes `stop()` instead of returning `packedFloat.wrap(0)`. In inline assembly, `stop()` is the EVM `STOP` opcode, which ends the **current call frame successfully** with no return data—not a normal function return. Because library functions are compiled into the caller’s execution context, this halts the whole transaction after `sqrt(0)`; no code after the call runs.
- **Impact:** Any code path that calls `sqrt` on a value that can be zero (e.g. `sqrt(collateral - debt)` when equal) silently succeeds and skips liquidation, transfers, or state updates below that call. This is a silent logic-break / griefing vector, not a safe “return zero” behavior.

```solidity
if iszero(a) {
    stop();
}
```

---

## ln(0) causes division by zero

- **Location:** `Ln.sol` : `ln` → `ln_helper`
- **Mechanism:** `ln` only special-cases a value encoded as `MIN_*_DIGIT_NUMBER` with a specific exponent (i.e. the canonical encoding of `1.0`), not literal zero. For `packedFloat.wrap(0)`, mantissa is `0` and the helper takes the main branch. After scaling, `mantissa` remains `0`, and the Taylor path eventually reaches `calculateQ1`, which does not guard against a zero mantissa. The reciprocal branch also computes `BASE_TO_THE_MAX_DIGITS_M_X_2 / mantissa` with no zero check.
- **Impact:** `ln(0)` reverts the transaction (panic / division by zero). An attacker or edge-case state can DoS any function that computes `ln(x)` without guaranteeing `x > 0` (utilization rates, implied yields, etc.).

---

## ln() accepts negative inputs without reverting

- **Location:** `Ln.sol` : `ln`
- **Mechanism:** `ln` never reads `MANTISSA_SIGN_MASK`. It extracts mantissa and exponent as unsigned magnitudes and proceeds as if the input were positive. There is no `require`/`revert` for negative values (unlike `sqrt`, which reverts on negative inputs).
- **Impact:** `ln(-x)` returns the same result as `ln(x)`. In a protocol using `ln` for pricing, solvency, or interest formulas, negative balances or manipulated signed encodings produce mathematically invalid results instead of reverting, enabling incorrect payouts or bypassing checks that assume invalid-domain inputs fail.

---

## add/sub exponent alignment overflows `exp(BASE, adj)` in assembly

- **Location:** `Float128.sol` : `add`, `sub` (assembly alignment blocks for M and L paths)
- **Mechanism:** When aligning mantissas to a common exponent, the code uses `exp(BASE, adj)` and `sdiv(man, exp(BASE, adj))` inside unchecked assembly. In Yul, `exp` is arbitrary-precision exponentiation truncated to 256 bits with **silent overflow**. For base 10, `10^78` exceeds `type(uint256).max`; overflow occurs when `adj ≥ 78`. In the M-size path, `adj = logical_exp_a - logical_exp_b - 38`, so a logical exponent gap of **≥ 116** overflows. That gap is well within the representable exponent range (±8192). On overflow, `exp` can become `0`, making `sdiv(x, 0)` revert, or a wrapped value, producing a corrupted mantissa before addition.
- **Impact:** Adding/subtracting two valid `packedFloat` values with a large exponent separation either **reverts** (DoS on liquidation, interest accrual, share conversion) or returns a **wrong sum/difference**, breaking accounting invariants.

---

## mul() exponent underflow wraps `rExp` in assembly

- **Location:** `Float128.sol` : `mul` (assembly block computing `rExp`)
- **Mechanism:** For the M path, `rExp := sub(add(shr(EXPONENT_BIT, aExp), shr(EXPONENT_BIT, bExp)), ZERO_OFFSET)`. This is unchecked assembly arithmetic. When both operands have very negative logical exponents (e.g. near the minimum `-8192`, raw exponent field `0`), `add(0, 0) - 8192` **underflows** and wraps to a huge `uint256`. Subsequent logic uses `rExp` in `gt(rExp, maxExp)` and normalization branches that decide M vs L format and scaling.
- **Impact:** Multiplying two tiny (but representable) values can take the wrong normalization branch and return a garbage `packedFloat` (wrong magnitude/exponent/format), corrupting balances, rates, or share math at exponent extremes.

---

## Non-canonical zero encodings bypass zero checks

- **Location:** `Float128.sol` : `add`, `sub`, `mul`, `div` (early-zero guards); `Float128.sol` : `eq`
- **Mechanism:** Zero is only recognized when `packedFloat.unwrap(x) == 0`. A word with **mantissa 0** but **non-zero exponent bits** (e.g. `packedFloat.wrap(1 << EXPONENT_BIT)`) is mathematically zero but `unwrap(x) != 0`. Such values skip early-zero fast paths and enter full arithmetic with `aMan == 0` but a non-trivial exponent field, yielding results that do not match true floating-point semantics. `eq` is raw bitwise equality, so canonical `wrap(0)` is not equal to these encodings.
- **Impact:** If a protocol stores user-supplied `packedFloat` values and uses `unwrap(x) == 0` or `eq(x, ZERO)` for “no balance / cleared position,” an attacker can supply a **phantom non-zero bit pattern representing 0** to bypass zero checks while still passing some bitwise validations, breaking invariants in deposit/withdraw or liquidation logic.

---

## toPackedFloat() does not validate exponent range

- **Location:** `Float128.sol` : `toPackedFloat`
- **Mechanism:** The function accepts any `int exponent` and encodes it as `shl(EXPONENT_BIT, add(exponent, ZERO_OFFSET))` without enforcing the documented `[-8192, +8191]` range. Out-of-range values shift exponent bits into the L-flag (bit 241), sign (bit 240), and high mantissa bits on `or(...)`, producing encodings that are not valid `packedFloat` values.
- **Mechanism (continued):** Downstream `decode`, comparisons, and arithmetic assume the bit layout from `Types.sol`; corrupted words produce nonsensical mantissa/exponent pairs.
- **Impact:** User-controlled `(mantissa, exponent)` input can craft **malformed encodings** that deserialize incorrectly and propagate through `add`/`mul`/`ln`, enabling accounting manipulation where encoders are permissionless.

---

## eq() uses bitwise equality, not mathematical equality

- **Location:** `Float128.sol` : `eq`
- **Mechanism:** `eq` compares the raw `uint256` word (`packedFloat.unwrap(a) == packedFloat.unwrap(b)`), not decoded numeric value. Unless every producer normalizes to a single canonical encoding (not enforced by the library), the same real number can have multiple representations differing in exponent/mantissa normalization or phantom-zero patterns.
- **Impact:** Authorization or solvency checks of the form `eq(userProvided, expected)` can be bypassed or fail incorrectly if a user supplies a different encoding of the same value, or a phantom-zero variant, affecting collateral checks, debt caps, or allowance-style comparisons.

---

## Summary

| Severity (typical) | Finding |
|---|---|
| Critical | `sqrt(0)` → `stop()` halts transaction |
| High | `ln(0)` division by zero (DoS) |
| High | `add`/`sub` alignment `exp()` overflow / div-by-zero |
| High | `mul` `rExp` underflow at min exponents |
| Medium | Non-canonical zero bypasses `unwrap == 0` checks |
| Medium | `ln` on negative inputs (silent wrong answer) |
| Medium | `toPackedFloat` out-of-range exponent bit corruption |
| Low–Medium | `eq` bitwise vs semantic equality |

**Not reported (by design):** truncation rounding in `div`, Taylor-series approximation error in `ln`, gas/style issues—these are precision or engineering tradeoffs unless a specific economic exploit path is shown.

**Recommendation for integrators:** Never use `unwrap(x) == 0` as the sole zero test; validate encodings on input; guard `sqrt`/`ln` domains explicitly; avoid relying on `eq` for numeric equality; treat `add`/`sub`/`mul` at extreme exponent boundaries as unsafe without additional bounds checks.

