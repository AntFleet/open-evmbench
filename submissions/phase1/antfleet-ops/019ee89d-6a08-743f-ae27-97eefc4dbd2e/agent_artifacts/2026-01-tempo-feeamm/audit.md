# Audit: 2026-01-tempo-feeamm

## Reentrancy in `burn` — interactions before effects drains the pool
- Location: contracts/FeeAMM.sol : `burn`
- Mechanism: `burn` executes `IERC20(userToken).transfer(to, amountUserToken)` and `IERC20(validatorToken).transfer(to, amountValidatorToken)` **before** it decrements `liquidityBalances[poolId][msg.sender]`, `totalSupply[poolId]`, and the pool reserves, and there is no reentrancy guard. If either pool token invokes a recipient/sender callback (ERC‑777‑style `tokensReceived`/`tokensToSend`, or any hookable TIP‑20 token), the attacker re‑enters `burn` with the same `liquidity` while `liquidityBalances`/`totalSupply`/reserves are still at pre‑burn values, so `_calculateBurnAmounts` recomputes the full payout each time. Each re‑entry pays out the attacker's share again; with `liquidity < totalSupply/2` the doubled payout fits within the pool's own reserves, so no cross‑pool balance is even needed. On unwind, `liquidityBalances[msg.sender] -= liquidity`, `totalSupply -= liquidity`, and `pool.reserve* -= ...` underflow silently (Solidity 0.7.6 has no checked arithmetic), wrapping the attacker's balance to ~2^128 and corrupting reserves.
- Impact: An attacker holding any LP position in a pool whose token has a transfer hook can recursively withdraw a multiple of their share, draining pool reserves (and shared-token balances of other pools).

## `mint` and `burn` value `userToken` inconsistently — a new LP skims existing LPs
- Location: contracts/FeeAMM.sol : `mint` (else branch) and `burn` / `_calculateBurnAmounts`
- Mechanism: `mint` prices shares against `denom = reserveValidatorToken + (N * reserveUserToken)/SCALE`, i.e. it values the pool's accumulated `userToken` at 0.9985. `burn` redeems that same `userToken` at par (`amountUserToken = liquidity * reserveUserToken / totalSupply`). Because `mint` accepts only `validatorToken`, an attacker deposits `a` validatorToken into a pool that has accumulated `userToken` from fee swaps, receives shares priced as if the userToken were worth 0.9985, then immediately `burn`s to claim that userToken at 1.0. The atomic profit is `a*(F−D)/(D+a)` where `F−D = 0.0015 * reserveUserToken`, approaching ~0.15% of `reserveUserToken` for large `a` — paid entirely by pre‑existing LPs. It is risk‑free, atomic, and flash‑loanable, requires no special token, and is repeatable.
- Impact: Any depositor can extract up to ~0.15% of a pool's `reserveUserToken` per mint→burn cycle directly from existing liquidity providers with zero market risk.

## Unchecked `transfer`/`transferFrom` return values
- Location: contracts/FeeAMM.sol : `executeFeeSwap`, `rebalanceSwap`, `mint`, `burn`
- Mechanism: Every `IERC20.transfer`/`transferFrom` result is ignored. For tokens that return `false` on failure instead of reverting, state mutates as if the transfer succeeded. In `mint`, the `transferFrom` is followed unconditionally by `pool.reserveValidatorToken += amountValidatorToken` and the share credit, minting free LP shares. In `rebalanceSwap`, `pool.reserveValidatorToken += uint128(amountIn)` and `pool.reserveUserToken -= uint128(amountOut)` are applied **before** the inbound `transferFrom`, and `userToken` is paid out regardless of whether the pull actually delivered funds. In `executeFeeSwap`, a silently failed inbound `transferFrom` still credits `reserveUserToken` and pays out `validatorToken`.
- Impact: With a non-reverting ERC‑20, an attacker mints LP shares or receives output tokens without delivering any input, draining pool reserves.

## Reentrancy in `executeFeeSwap` — input pulled before reserves update
- Location: contracts/FeeAMM.sol : `executeFeeSwap`
- Mechanism: The liquidity check `require(pool.reserveValidatorToken >= amountOut)` and the `IERC20(userToken).transferFrom(msg.sender, address(this), amountIn)` pull both run **before** `reserveUserToken`/`reserveValidatorToken` are updated. With a sender‑callback token (ERC‑777 `tokensToSend`), the attacker re‑enters during the pull; the still‑stale `reserveValidatorToken` passes the check again, so the same reserves are paid out a second time. On unwind, `pool.reserveValidatorToken -= uint128(amountOut)` underflows to a near‑max `uint128`.
- Impact: The attacker receives `validatorToken` exceeding the pool's reserve (drawing on the same token held for other pools) and permanently corrupts the pool's reserve accounting.

## Reserve accounting breaks for fee-on-transfer / rebasing tokens
- Location: contracts/FeeAMM.sol : `mint`, `executeFeeSwap`, `rebalanceSwap` (the `reserve += amount` updates)
- Mechanism: Reserves are tracked from the requested amounts (`reserve += amountIn` / `amountValidatorToken`) rather than the measured balance delta. A fee-on-transfer token delivers less than the requested amount, and a down-rebasing token shrinks the held balance, so recorded reserves exceed real holdings while all payouts (`burn`, `rebalanceSwap`, `executeFeeSwap`) are computed from the inflated reserves.
- Impact: Withdrawal `transfer` calls eventually revert once recorded reserves outrun the real balance, leaving the pool insolvent against its books and stranding the funds of whoever exits last.

