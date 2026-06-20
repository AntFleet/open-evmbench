# Audit: 2026-01-tempo-feeamm

## Reentrant `burn` lets an LP redeem the same liquidity multiple times
- Location: `contracts/FeeAMM.sol : burn` (lines 243-258)
- Mechanism: `burn` transfers both pool tokens out before it decrements `liquidityBalances`, `totalSupply`, or the pool reserves. If either token or the `to` recipient can execute a callback during `transfer` (for example via an ERC777-style hook or a malicious ERC20), the LP holder contract can re-enter `burn` while its LP balance is still unchanged and have `_calculateBurnAmounts` price the second redemption off the pre-burn reserves. Because this contract is compiled under Solidity 0.7.6, the later `-=` operations are unchecked; once an inner call has already reduced the balance, outer frames underflow instead of reverting.
- Impact: A contract LP can recursively burn the same liquidity over and over and drain most or all reserves from the pool.

## `rebalanceSwap` sells user-token reserves below par to anyone
- Location: `contracts/FeeAMM.sol : rebalanceSwap` (lines 139, 152-162)
- Mechanism: `amountIn` is computed as `(amountOut * 9985) / 10000 + 1`, so for non-trivial trades the caller pays only about `99.85%` of the `amountOut` they receive. For two USD stablecoins, that is a standing subsidy: the function lets any caller buy `userToken` from the pool at a discount, and the `+1` only offsets dust rounding, not the 15 bps underpricing. There is no access control, auction, or reserve-ratio logic limiting who can take that spread.
- Impact: An attacker can repeatedly call `rebalanceSwap`, sell the received `userToken` externally at roughly 1:1, and drain the pool’s accumulated `userToken` reserves at LP expense.

## LP minting is cheaper than LP redemption, enabling mint/burn value extraction
- Location: `contracts/FeeAMM.sol : mint / burn / _calculateBurnAmounts` (lines 194-196, 243-258, 280-285)
- Mechanism: For an existing pool, `mint` prices new LP shares against `reserveValidatorToken + 0.9985 * reserveUserToken`, but `burn` redeems those shares against the full `reserveValidatorToken + reserveUserToken`. That means `reserveUserToken` is discounted on entry but not on exit. A new LP can deposit validator tokens, receive too many LP shares, and immediately burn them for a pro-rata claim on the undiscounted pool. This is a pure accounting mismatch between the mint and burn formulas.
- Impact: A rational attacker can cycle `mint -> burn` to siphon value from incumbent LPs, extracting part of the pool’s `userToken` inventory without taking market risk.

## The AMM hardcodes near-1:1 pricing and has no depeg/oracle defense
- Location: `contracts/FeeAMM.sol : executeFeeSwap / rebalanceSwap` (lines 103, 139)
- Mechanism: Both swap directions use fixed constants instead of market price, reserve ratio, or any oracle. `executeFeeSwap` always values `userToken` at `0.997` validator tokens, and `rebalanceSwap` always values `validatorToken` at about `0.9985` user tokens, regardless of whether one “stablecoin” has depegged. The contract comments assume all assets stay at USD parity, but that assumption is never enforced on-chain.
- Impact: If any supported stablecoin trades below par, an attacker can buy the depegged asset cheaply off-chain and swap it into the pool for healthier stablecoins until the good side is exhausted.

## Raw ERC20 calls and nominal reserve accounting allow unpaid or short-paid deposits to be booked as full reserves
- Location: `contracts/FeeAMM.sol : executeFeeSwap / rebalanceSwap / mint / burn` (lines 113-118, 157-162, 205-214, 252-253)
- Mechanism: The contract uses bare `IERC20.transfer` / `transferFrom` and ignores the returned `bool`. It also updates reserves by the requested amount instead of the actual balance delta received. If a token returns `false`, charges a transfer fee, rebases during transfer, or otherwise delivers less than requested, the function still treats the transfer as fully successful and mutates pool accounting accordingly.
- Impact: Pool reserves can become overstated and insolvent; LP shares can be minted against less collateral than assumed; and in pools involving non-standard tokens, attackers can receive outputs or LP claims without paying the full economic input.

