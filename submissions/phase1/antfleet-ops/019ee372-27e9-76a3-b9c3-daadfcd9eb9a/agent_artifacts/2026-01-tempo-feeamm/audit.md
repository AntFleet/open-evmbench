# Audit: 2026-01-tempo-feeamm

Here are the main security vulnerabilities found in the contract:

## Reentrancy in `burn` function allows pool draining
- **Location:** `FeeAMM.sol` : `burn`
- **Mechanism:** The `burn` function calculates the token amounts to return to the user and executes the external token transfers (`IERC20(...).transfer(to, ...)`) before it decreases the user's `liquidityBalances`, the `totalSupply`, and the internal `pool.reserve` variables. This heavily violates the Checks-Effects-Interactions (CEI) pattern. If either the `userToken` or `validatorToken` supports transfer hooks (e.g., ERC-777, ERC-677, or custom proxy implementations with pre/post-transfer callbacks), the receiving contract (`to`) will receive execution control mid-transaction.
- **Impact:** An LPs contract can reenter the `burn()` function within the transfer callback. Because their `liquidityBalances` and the pool reserves have not yet been mutated, the system recalculates the exact same output amounts and issues the transfer again. The attacker can loop this behavior to continuously withdraw funds using the same liquidity shares, entirely draining the pool's reserves limits.
