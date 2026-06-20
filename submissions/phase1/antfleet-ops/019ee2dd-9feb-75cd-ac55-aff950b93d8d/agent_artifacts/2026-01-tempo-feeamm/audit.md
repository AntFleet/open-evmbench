# Audit: 2026-01-tempo-feeamm

 ## Reentrancy / checks-effects-interactions violations
- Location: `contracts/FeeAMM.sol` : `burn`, `executeFeeSwap`, `mint`
- Mechanism: `burn` transfers `userToken` and `validatorToken` to `to` before decrementing `liquidityBalances[poolId][msg.sender]`, `totalSupply[poolId]`, and the pool reserves. `executeFeeSwap` and `mint` call `transferFrom` before updating reserves or liquidity. If any involved token implements a pre- or post-transfer hook (ERC777/ERC677/etc.), the hook runs while the contract is in an intermediate state and can reenter other functions with stale balances or reserves.
- Impact: In `burn`, a callback recipient can burn the same LP shares repeatedly and drain both reserves. In `executeFeeSwap`, a reentrant swap can reduce `reserveValidatorToken` before the outer update, causing an underflow in the `<0.8.0` arithmetic and corrupting pool accounting. In `mint`, a reentrant mint uses the pre-deposit denominator and can receive more liquidity than entitled.

## Unchecked ERC20 transfer return values
- Location: `contracts/FeeAMM.sol` : `executeFeeSwap`, `rebalanceSwap`, `mint`, `burn`
- Mechanism: Every token movement uses bare `IERC20.transfer`/`transferFrom` without checking the returned `bool` and without OpenZeppelin `SafeERC20`. Tokens that signal failure by returning `false` will not revert, while tokens such as USDT that return no data will cause the call to revert or decode incorrectly.
- Impact: For tokens that return `false`, reserves and liquidity balances are updated as if the transfer succeeded even though no tokens moved, creating balance/insolvency mismatches. For USDT-like stablecoins the swap and liquidity functions are effectively unusable.

## Single-sided mint misprices userToken reserves
- Location: `contracts/FeeAMM.sol` : `mint`, `_calculateBurnAmounts`
- Mechanism: `mint` accepts only `validatorToken` and issues liquidity with `liquidity = (amountValidatorToken * totalSupply) / (reserveValidatorToken + N*reserveUserToken/SCALE)`. Because `N < SCALE`, the existing `userToken` reserve (which includes fees collected from users) is valued below a 1:1 stablecoin basis, while `burn` redeems a pro-rata share of the full `reserveUserToken` and `reserveValidatorToken`.
- Impact: A caller can mint validator-token liquidity and immediately burn it to capture `userToken` reserves at a discount, draining the fee inventory and unfairly diluting existing liquidity providers.

## Silent integer overflow in reserve and liquidity math
- Location: `contracts/FeeAMM.sol` : `executeFeeSwap`, `mint`, `_calculateBurnAmounts`
- Mechanism: The pragma is `<0.8.0` and no SafeMath is used. `executeFeeSwap` adds `amountIn` to `pool.reserveUserToken` with only a per-input `uint128` check, so cumulative reserves can silently wrap. `mint` does the same with `pool.reserveValidatorToken`, and intermediate products such as `amountValidatorToken * totalSupply` in `mint` and `liquidity * reserve` in `_calculateBurnAmounts` can overflow `uint256` before the subsequent `uint128` checks.
- Impact: Overflow corrupts reserve and LP-share accounting, producing incorrect mint amounts, zeroed or inflated reserves, and burn/swap outcomes that diverge from the contract’s actual token balances.
