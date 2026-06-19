# Audit: 2024-07-basin

## Unrestricted upgrades of upgradeable Wells
- Location: `src/WellUpgradeable.sol` : `_authorizeUpgrade`, `upgradeTo`, `upgradeToAndCall`
- Mechanism: The upgrade path never checks `msg.sender` or `onlyOwner`. `_authorizeUpgrade` only verifies that the call is executing through the proxy/clone structure and that `newImplementation` is an Aquifer-registered Well with a valid `proxiableUUID`. Since Aquifer deployment is permissionless, an attacker can register a malicious compatible Well and call `upgradeTo` / `upgradeToAndCall` on a victim upgradeable Well.
- Impact: Any account can replace the implementation used by an upgradeable Well, change its token/function configuration, or execute malicious upgrade calldata. This can lead to complete theft of assets held by the Well/proxy.

## Public reinitializer can reset the reentrancy guard
- Location: `src/WellUpgradeable.sol` : `init`, `initNoWellToken`
- Mechanism: `initNoWellToken()` marks the contract initialized at version 1, while `init()` remains externally callable as `reinitializer(2)`. During a token callback or other external-control point inside a `nonReentrant` Well operation, an attacker can call `init()`, which executes `__ReentrancyGuard_init()` and resets the guard status while the outer protected function is still active.
- Impact: For Wells deployed with `initNoWellToken`, an attacker can bypass `nonReentrant` once and reenter swap/liquidity flows while reserves are stale. This can allow double accounting and draining of pool tokens, especially through remove-liquidity paths that transfer tokens before final reserve updates.

## Two-token Well functions allow free withdrawal of extra tokens
- Location: `src/Well.sol` : `removeLiquidityImbalanced`; `src/functions/ConstantProduct2.sol` / `src/functions/Stable2.sol` : `calcLpTokenSupply`; `src/functions/ProportionalLPToken2.sol` : `calcLPTokenUnderlying`
- Mechanism: The factory and `Well.init` do not enforce that `ConstantProduct2` or `Stable2` are only used with exactly two tokens. These functions only account for `reserves[0]` and `reserves[1]`. In a Well configured with three or more tokens, `removeLiquidityImbalanced` transfers every requested token amount first, then computes `lpAmountIn` from a Well function that ignores reserves beyond index 1.
- Impact: In any misconfigured Well using a two-token function with extra tokens, an attacker can set `tokenAmountsOut` for token index `>= 2`, withdraw those tokens, and burn `0` LP because the LP supply calculation is unchanged. All extra-indexed reserves can be drained.

## Stable2 defaults token1 decimals incorrectly
- Location: `src/functions/Stable2.sol` : `decodeWellData`
- Mechanism: The second defaulting check repeats `decimal0 == 0` instead of checking `decimal1 == 0`:
  ```solidity
  if (decimal0 == 0) {
      decimal1 = 18;
  }
  ```
  As a result, encoded data using `0` to mean “18 decimals” works for token0 but not token1. Token1 remains `0` decimals and is scaled by `1e18` in `getScaledReserves`.
- Impact: Stable2 pools using the documented/default zero value for token1 decimals are priced with token1 reserves inflated by `1e18`. Swaps, liquidity minting, and withdrawals become massively mispriced, allowing attackers to extract value from LPs in affected pools.

## Stable2 oracle rate precision corrupts MultiFlowPump caps
- Location: `src/functions/Stable2.sol` : `calcRate`, `calcReserveAtRatioSwap`; `src/pumps/MultiFlowPump.sol` : `_capRates`, `calcReservesAtRatioSwap`, `tryCalcReserveAtRatioSwap`
- Mechanism: `MultiFlowPump` treats `calcRate` output as a ratio against `CAP_PRECISION = 1e18` and passes `ratios[i] = rLimit`, `ratios[j] = 1e18` into `calcReserveAtRatioSwap`. `Stable2.calcRate`, however, returns a 6-decimal marginal amount, not an `1e18`-scaled ratio. `Stable2.calcReserveAtRatioSwap` then computes a near-zero `targetPrice`, causing the LUT lookup to revert; `MultiFlowPump.tryCalcReserveAtRatioSwap` catches that failure and substitutes `type(uint256).max`.
- Impact: A rate-capped Stable2 oracle update can store or use astronomically incorrect capped reserves instead of reverting. Downstream protocols reading the pump can receive corrupted instantaneous/cumulative reserves and make incorrect pricing or collateral decisions.

