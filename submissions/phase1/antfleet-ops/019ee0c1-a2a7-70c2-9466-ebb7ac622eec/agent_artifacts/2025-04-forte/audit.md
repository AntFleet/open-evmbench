# Audit: 2025-04-forte

## Natural log accepts non-positive inputs
- Location: `src/Ln.sol` : `ln`
- Mechanism: `ln` extracts only the L flag, mantissa, and exponent from `input` and never checks `MANTISSA_SIGN_MASK` or rejects a zero mantissa. The sign bit is stripped by `mantissa := and(input, MANTISSA_MASK)`, so negative values are processed as their absolute value; the `ln(1)` shortcut also makes `ln(-1)` return zero.
- Impact: Contracts using `ln` for pricing, risk curves, interest, or invariant math can receive finite outputs for undefined inputs. An attacker can feed negative or zero values and bypass expected domain failures, corrupting downstream accounting or threshold checks.

## `sqrt(0)` halts execution successfully
- Location: `src/Float128.sol` : `sqrt`
- Mechanism: The zero branch uses raw EVM `stop()` instead of returning `packedFloat.wrap(0)` or reverting. `STOP` ends the entire current call frame with success and empty returndata; it does not return control to the Solidity caller.
- Impact: Any contract path that calls `sqrt(0)` after making state changes will silently skip all logic after the call while still succeeding. This can bypass later validation, accounting updates, or transfers that the caller assumes always execute.

## Equal numeric values compare unequal across M/L encodings
- Location: `src/Float128.sol` : `le`, `ge`, `eq`
- Mechanism: `eq` compares raw packed words, not numeric value. `le` and `ge` return true only for raw equality, then use strict `<` / `>` after normalizing M operands to L precision. Two valid encodings of the same number, such as M `1e37 * 10^-37` and L `1e71 * 10^-71`, normalize to identical mantissa/exponent pairs but still make `le` and `ge` return false.
- Impact: Contracts relying on `<=`, `>=`, or `==` for caps, collateral checks, liquidation thresholds, or boundary conditions can reject or accept the wrong branch when attackers choose an equivalent representation with a different mantissa size.

## Mixed M/L operations can underflow promoted exponents
- Location: `src/Float128.sol` : `add`, `sub`, `mul`, `div`, `lt`, `le`, `gt`, `ge`
- Mechanism: When a medium mantissa operand is combined with a large mantissa operand, the code promotes M to L by multiplying the mantissa by `10^34` and subtracting `DIGIT_DIFF_L_M` from the encoded exponent. For M values whose raw exponent is below `34`, this unsigned subtraction underflows and turns an extremely small exponent into a near-maximum exponent.
- Impact: Tiny attacker-controlled M values can be treated as enormous values in mixed-size arithmetic or comparisons. This can corrupt price/math outputs or invert threshold checks whenever user input or prior operations can produce low-exponent M values.

