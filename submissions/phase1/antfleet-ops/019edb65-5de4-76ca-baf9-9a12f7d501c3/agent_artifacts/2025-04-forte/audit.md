# Audit: 2025-04-forte

## <DoS via `sqrt(0)` due to `stop()`>
- Location: `Float128.sol` : `sqrt`
- Mechanism: In the assembly block, after checking that the input is not negative, the code checks `if iszero(a) { stop() }`. The `stop()` opcode halts execution of the entire call, consuming all remaining gas. The function should return the zero `packedFloat` (e.g., `packedFloat.wrap(0)`) instead of halting.
- Impact: Any transaction that calls `sqrt` with a zero argument (or any function that internally uses `sqrt` on a zero value) will be terminated with a hard stop, wasting all gas and causing a denial of service. This can be exploited to disrupt protocol operations.

## <Incorrect `lt` and `gt` for zero vs zero>
- Location: `Float128.sol` : `lt`, `gt`
- Mechanism: When both inputs are zero, the zero‑handling branch in `lt` evaluates `and(isAZero, iszero(bNeg))` (both true), causing `lt(0,0)` to return `true`. Similarly, `gt` returns `true` for `gt(0,0)`. The correct result should be `false` because zero is neither less than nor greater than itself.
- Impact: Contracts that rely on these comparison functions for sorting or conditional logic will behave incorrectly. This can lead to logical errors, such as incorrect ordering of zero in a list, which may be exploited to manipulate protocol state.

## <`toPackedFloat` reverts on mantissas with fewer than 38 digits>
- Location: `Float128.sol` : `toPackedFloat`
- Mechanism: The function computes `mantissaMultiplier := sub(digitsMantissa, MAX_DIGITS_M)`. If `digitsMantissa < MAX_DIGITS_M` (38), the subtraction underflows and reverts in Solidity 0.8.x. The function should instead handle shorter mantissas by multiplying them to 38 digits and adjusting the exponent.
- Impact: Any attempt to pack a number whose mantissa has fewer than 38 significant digits (e.g., `1`, `0.5`, `12345`) will revert, making the library unusable for a huge class of typical values. This is a critical flaw that breaks core functionality of the floating‑point library.

## <`ln` does not reject non‑positive inputs>
- Location: `Ln.sol` : `ln`
- Mechanism: The natural logarithm is undefined for zero and negative numbers. The function lacks any check that the input is strictly positive. For zero, `ln` will proceed to `ln_helper` with a zero mantissa, causing a division by zero or other low‑level revert. For negative numbers, it will compute an invalid result without warning.
- Impact: A contract that calls `ln` with a user‑supplied value ≤ 0 may experience unexpected reverts or produce garbage results. If the result is used in pricing or financial calculations, this can lead to loss of funds or incorrect protocol state.

## <`ln_helper` can revert due to overflow in `z_int` calculation>
- Location: `Ln.sol` : `ln_helper` (line `z_int = 10 ** 76 - int(mantissa)`)
- Mechanism: The algorithm scales `mantissa` into the range `(0.986·10^76, 10^76]` and then computes `z_int = 10**76 - int(mantissa)`. If due to rounding errors or edge cases the scaled mantissa exceeds `10**76`, the subtraction underflows (Soliidty 0.8 checked arithmetic) and reverts. This can happen for certain inputs that push the scaled mantissa just above the upper bound.
- Impact: An attacker can craft a specific input that triggers the overflow, causing a revert and denial of service. Because the function is used in financial contexts, such a revert could block critical operations.
