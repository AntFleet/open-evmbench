# Audit: 2025-04-forte

## EVM STOP Opcode in Square Root Evaluation Halts Entire Transaction
- Location: `Float128.sol` : `sqrt`
- Mechanism: In the inline assembly block of the `sqrt` function, there is an early validation statement: `if iszero(a) { stop() }`. In the EVM, the `stop` opcode (0x00) halts execution in the current frame successfully and discards any remaining steps. Since `Float128` is an `internal` library, its code is compiled directly into the caller contract's context rather than executed as an external message call body. Consequently, calling `sqrt` with a zero argument will forcibly terminate the execution of the entire transaction immediately with a success status.
- Impact: Any caller transaction that performs a square root operation resulting in `0` will instantly abort mid-execution and report success, entirely skipping all subsequent business logic, fund transfers, state mutations, and security checks.

## Lack of Sanity Checks on Zero/Negative Inputs in Natural Logarithm
- Location: `Ln.sol` : `ln` / `ln_helper`
- Mechanism: Natural logarithm mathematically requires $x > 0$. However, the `ln` function accepts negative numbers or zero without throwing a revert. For negative numbers, since `mantissa` is isolated using `and(input, MANTISSA_MASK)` (which masks bits 0 to 239) and the sign is held at bit 240, the sign bit is completely ignored, and the logarithm of the positive absolute value is calculated. For zero inputs, the function enters `ln_helper` where a zero mantissa yields $z\_int = 10^{76}$, evaluating through the Taylor series loop and ultimately returning a mock positive value.
- Impact: Undefined mathematical calculations successfully return mock values instead of reverting. Attackers can inject zero or negative values into token valuation, pool exchange rate curves, or leverage indexes to generate corrupt metrics to steal funds or break protocol invariants.

## Uncontrolled 256-bit Exponent Underflow in Add, Sub, and Mul Fractions
- Location: `Float128.sol` : `add` / `sub` / `mul`
- Mechanism: In `add` (and `sub`), the function normalizes the two addends by subtracting `38 << 242` or `34 << 242` from the exponent mask. Similarly, in `mul`, the exponent of the product is computed from `sub(add(shr(242, aExp), shr(242, bExp)), ZERO_OFFSET)`. If the inputs carry underflow-prone exponents (close to $-8192$), these subtractions wrap around modulo $2^{256}$. This corrupted, massive value is later shifted back via `shl(EXPONENT_BIT, rExp)`, which truncates the value to a major positive exponent, distorting math operations (e.g., adding or multiplying two tiny numbers like $10^{-8000}$ results in a massive positive output like $10^{8200}$).
- Impact: Arithmetic operations on extremely small numbers bypass overflow/underflow boundaries silently and produce massive corrupted numbers, letting users manipulate balance updates, trigger fake liquidations, or break monetary constraints.

## Exponent Underflow in Size-M vs Size-L Comparison Operators
- Location: `Float128.sol` : `lt` / `le` / `gt` / `ge`
- Mechanism: When comparing an M-size `packedFloat` with an L-size `packedFloat`, the comparison operators scale the M-size number to L-size. To do so, they subtract `34` (shifted by 242 bits) from `aExp`. If the original M-size exponent is within 34 steps of the minimum representation (range `[-8192, -8159]`), the subtraction wraps around modulo $2^{256}$. This wrapping error shifts the high bits of `aExp` and sets bit 255. The function's internal unsigned `lt` and `gt` statements then read the underflowed exponent as an extremely large positive value, which incorrectly flips the direction of the comparison.
- Impact: Critical financial comparison assertions (evaluating collateral health, maximum withdrawal caps, or lock constraints) return incorrect boolean values, allowing attackers to drain funds or bypass validation checks.
