# Audit: 2024-07-basin

## removeLiquidityImbalanced transfers before slippage check
- Location: src/Well.sol : removeLiquidityImbalanced
- Mechanism: The function performs `safeTransfer` of every `tokenAmountsOut[i]` (and mutates the local `reserves` array) before computing `lpAmountIn = totalSupply() - _calcLpTokenSupply(...)` and the subsequent `if (lpAmountIn > maxLpAmountIn) revert` (and the `_burn`). The external ERC-20 calls therefore complete even when the check fails.
- Impact: Any caller can cause the Well to permanently lose arbitrary token balances (recipient receives the tokens while no LP is burned and the revert leaves the Well's accounting inconsistent); repeated calls drain the entire pool.

## removeLiquidityImbalanced lacks reentrancy protection on the burn path after external calls
- Location: src/Well.sol : removeLiquidityImbalanced
- Mechanism: Although the function is decorated `nonReentrant`, the `safeTransfer` loop executes before the `if` check and `_burn`. A malicious token (or a token that performs a callback) can re-enter the Well between the transfers and the revert, observing an inconsistent reserve state.
- Impact: Attacker can re-enter to perform additional privileged operations (e.g., another `removeLiquidity*` call) that observe stale reserves or bypass the `maxLpAmountIn` check, enabling further drainage.

## WellUpgradeable upgrade authorization accepts any previously-used implementation address
- Location: src/WellUpgradeable.sol : _authorizeUpgrade
- Mechanism: The check `IAquifer(aquifer).wellImplementation(newImplementation) != address(0)` only verifies that `newImplementation` appears as a value in the Aquifer mapping; it does not verify that `newImplementation` is the actual well implementation that was cloned, nor does it prevent an arbitrary contract that was once used as an implementation from being supplied.
- Impact: The Well owner (or a compromised owner) can upgrade the proxy to a malicious contract that satisfies the (weak) mapping check, giving the attacker full control over the Well's storage and funds.
