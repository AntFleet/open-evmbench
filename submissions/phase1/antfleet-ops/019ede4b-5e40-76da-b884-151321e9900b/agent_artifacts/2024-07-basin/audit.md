# Audit: 2024-07-basin

## Stable2 Default Decimals Logic Error
- Location: `src/functions/Stable2.sol` : `decodeWellData`
- Mechanism: The function intends to default both token decimals to 18 if they are passed as 0. However, due to a copy-paste error, it checks `if (decimal0 == 0)` twice instead of checking `if (decimal1 == 0)` for the second token. As a result, if `decimal1` is passed as 0, it is never updated to 18 and remains 0. This causes `getScaledReserves` to artificially scale the second token's reserves by `10**18` instead of `10**0`, completely breaking the Stableswap invariant math for that pool.
- Impact: An attacker can exploit the massive pricing discrepancy to drain the pool of its assets via arbitrage, or the pool will simply become unusable/broken if initialized with 0 for the second token's decimals expecting the 18-decimal default.

## WellUpgradeable Authorization Permanently Bricks Upgrades
- Location: `src/WellUpgradeable.sol` : `_authorizeUpgrade`
- Mechanism: The upgrade authorization check attempts to verify that the proxy was bored by a trusted Aquifer by calling `IAquifer(aquifer).wellImplementation(_getImplementation())`. However, `_getImplementation()` returns the *implementation* address, while the Aquifer's `wellImplementation` mapping expects a *proxy* (Well) address as the key and returns the implementation address. Passing the implementation address returns `address(0)`. The function then requires `address(0) == ___self` (where `___self` is the original implementation address), which will always evaluate to false and revert.
- Impact: The `upgradeTo` and `upgradeToAndCall` functions will always revert. The upgradeability feature of `WellUpgradeable` is completely broken, meaning any deployed upgradeable Wells can never be upgraded to fix future bugs or add features.

## LibBytes16 Memory Corruption Breaks MultiFlowPump Oracle
- Location: `src/libraries/LibBytes16.sol` : `readBytes16`
- Mechanism: When unpacking `bytes16` values from storage, the function correctly shifts and masks the lower 128 bits for even-indexed elements (`i & 1 == 0`). However, for odd-indexed elements (the first, third, etc., `bytes16` in a slot), it uses `mstore(..., sload(...))` without masking the lower 128 bits. In Solidity, `bytes16` is left-aligned in memory, meaning the lower 128 bits must be zero. Leaving them dirty corrupts the `bytes16` value. When `ABDKMathQuad` later casts this corrupted `bytes16` to `uint128`, it reads the dirty lower 128 bits instead of the actual value.
- Impact: This silently corrupts the EMA and cumulative reserve calculations for the first token (and any odd-indexed tokens) inside the `MultiFlowPump`. The Time-Weighted Average (TWA) oracle will report completely incorrect prices, allowing attackers to easily manipulate the oracle and exploit downstream protocols (like Beanstalk) that rely on it for manipulation-resistant pricing.
