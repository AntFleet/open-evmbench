# Audit: 2026-01-tempo-feeamm

## Mint/burn share accounting mismatch lets a flash deposit drain existing LPs
- Location: `contracts/FeeAMM.sol` : `mint` (else branch) vs `burn` / `_calculateBurnAmounts`
- Mechanism: When minting into a non-empty pool, the share calculation values the user-token reserve at a *discount* via the rebalance fee factor `N`:
  ```
  product = (N * reserveUserToken) / SCALE;        // 0.9985 * U
  denom   = reserveValidatorToken + product;       // V + 0.9985*U  (< V + U)
  liquidity = amountValidatorToken * _totalSupply / denom;
  ```
  But `burn` redeems shares against the reserves at *full proportional value* (`liquidity * reserveX / totalSupply` for both tokens). Because mint uses a denominator strictly smaller than the true pool value `V + U` whenever `U > 0`, a depositor receives more LP shares than the value they contributed, and then redeems those shares for a full proportional slice of *both* reserves. Net value extracted per round-trip is `a * (0.0015 * U) / (V + 0.9985*U + a) > 0` for any `U > 0`.
- Impact: Once the pool has accumulated any user-token reserve (which it always does, since `executeFeeSwap` pushes user tokens into the pool while `mint` is single-sided validator-token only), an attacker can repeatedly `mint` then immediately `burn` to siphon the user-token reserve that belongs to existing liquidity providers, with no price/slippage exposure. Iterating drains the user-token side of the pool.

## Reentrancy in `burn` (state updated after external transfers)
- Location: `contracts/FeeAMM.sol` : `burn`
- Mechanism: `burn` performs the two `IERC20(...).transfer(to, ...)` payouts **before** it decrements `liquidityBalances[poolId][msg.sender]`, `totalSupply[poolId]`, and the pool reserves. The CEI ordering is violated:
  ```
  IERC20(userToken).transfer(to, amountUserToken);
  IERC20(validatorToken).transfer(to, amountValidatorToken);
  liquidityBalances[poolId][msg.sender] -= liquidity;   // happens last
  ...
  ```
  If either token grants the recipient control during transfer (transfer hook / ERC777-style callback, or a malicious/upgradeable token deployed as a pool token), the attacker (who controls `to`) can re-enter `burn` while their LP balance still reflects the un-burned `liquidity`, withdrawing reserves multiple times against a single balance.
- Impact: Multi-withdrawal of pool reserves, draining the pool. Severity is gated on the token implementing a transfer callback, but the contract makes no assumption restricting pool tokens to callback-free ERC20s.

## ERC20 transfer/transferFrom return values are never checked
- Location: `contracts/FeeAMM.sol` : `executeFeeSwap`, `rebalanceSwap`, `mint`, `burn`
- Mechanism: Every token movement uses the raw `IERC20.transfer` / `transferFrom` and discards the boolean return. For tokens that signal failure by returning `false` instead of reverting, a failed `transferFrom` (e.g. in `executeFeeSwap` or `mint`) does not abort the call, yet the contract still credits the pool reserves and mints liquidity / pays out the counter-asset.
- Impact: An attacker using a non-reverting "false-on-failure" token (a permitted pool asset under a generic TIP-20 set) can credit reserves and receive liquidity shares or output tokens without actually delivering the input tokens, inflating shares or draining the other reserve.

## Unchecked uint128 reserve accumulation can wrap (Solidity <0.8.0)
- Location: `contracts/FeeAMM.sol` : `executeFeeSwap` (`pool.reserveUserToken += uint128(amountIn)`), `mint` (`pool.reserveValidatorToken += uint128(amountValidatorToken)`)
- Mechanism: The contract compiles under `>=0.7.6 <0.8.0`, so arithmetic has no built-in overflow protection. `_requireU128` only bounds each individual `amount` to `type(uint128).max`; it does not bound the *sum* with the existing reserve. `rebalanceSwap` explicitly guards its addition (`reserveValidatorToken + amountIn > type(uint128).max → revert`), but the `+=` updates in `executeFeeSwap` and `mint` have no such guard and will silently wrap on overflow.
- Impact: A reserve that grows past `2^128-1` wraps to a tiny value, corrupting pool accounting (mispriced swaps/mints, under-collateralized burns). Practically reachable only with token amounts at the `uint128` boundary, so this is the lowest-severity item, but the asymmetry with `rebalanceSwap`'s explicit check shows the guard was simply omitted.

