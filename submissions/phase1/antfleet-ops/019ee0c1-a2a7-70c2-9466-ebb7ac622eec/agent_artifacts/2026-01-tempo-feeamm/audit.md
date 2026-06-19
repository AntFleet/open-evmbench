# Audit: 2026-01-tempo-feeamm

## Unchecked ERC20 transfers allow swaps without payment
- Location: `contracts/FeeAMM.sol` : `executeFeeSwap`, `rebalanceSwap`, `mint`
- Mechanism: The contract calls `transfer` and `transferFrom` through `IERC20` but never checks the returned boolean and never verifies the actual balance delta received. In `executeFeeSwap`, reserves are credited with `amountIn` even if `userToken.transferFrom` returns `false` or transfers less than `amountIn`. In `rebalanceSwap`, the pool credits `amountIn` of `validatorToken` before an unchecked `transferFrom`. In `mint`, LP shares are minted from the nominal `amountValidatorToken`, not the amount actually received.
- Impact: A malicious, false-returning, or fee-on-transfer token can be paired with a valuable token and used to drain the valuable side of the pool. The attacker can receive `validatorToken` from `executeFeeSwap`, receive `userToken` from `rebalanceSwap`, or mint undercollateralized LP shares in `mint` without depositing the full expected asset amount.

## Reentrant burn can withdraw the same LP position multiple times
- Location: `contracts/FeeAMM.sol` : `burn`
- Mechanism: `burn` transfers `userToken` and `validatorToken` before reducing `liquidityBalances`, `totalSupply`, or pool reserves. A malicious token contract used as either pool token can reenter `burn` during `IERC20(...).transfer(...)`. Because the caller’s LP balance and reserves have not yet been updated, the nested call passes the same balance check and calculates withdrawals against the same pre-burn state.
- Impact: An attacker holding LP shares in a pool containing a reentrant token can burn the same liquidity repeatedly and withdraw more than their share, including draining the honest paired token. Because this is Solidity `<0.8.0`, repeated post-reentrancy subtractions can also underflow instead of reverting, further corrupting accounting.

## Reentrant fee swap can overdraw validator reserves
- Location: `contracts/FeeAMM.sol` : `executeFeeSwap`
- Mechanism: `executeFeeSwap` calls `userToken.transferFrom` before updating `reserveUserToken` and `reserveValidatorToken`. A malicious `userToken` can reenter `executeFeeSwap` from `transferFrom`; each nested call observes the same undecremented `reserveValidatorToken` and can pass the liquidity check for `amountOut`.
- Impact: A pool containing a malicious `userToken` and valuable `validatorToken` can have its validator-token reserve drained through nested swaps. The stored validator reserve may also underflow on unwind under Solidity `<0.8.0`.

## Reserve additions can wrap `uint128` accounting
- Location: `contracts/FeeAMM.sol` : `executeFeeSwap`, `mint`
- Mechanism: `_requireU128(amount)` only checks that the incoming amount fits in `uint128`; it does not check that `pool.reserveUserToken + amountIn` or `pool.reserveValidatorToken + amountValidatorToken` still fits in `uint128`. In Solidity `<0.8.0`, these additions wrap silently.
- Impact: An attacker able to push a reserve near `type(uint128).max` can wrap the recorded reserve to a small value while the actual token balance remains high. This breaks LP share valuation, burn accounting, and future swap liquidity checks, allowing pool accounting corruption and potential theft from later liquidity providers or swappers.

