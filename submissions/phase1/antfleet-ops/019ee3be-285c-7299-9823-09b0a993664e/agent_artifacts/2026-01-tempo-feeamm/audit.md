# Audit: 2026-01-tempo-feeamm

## Reentrancy in Burn via Unsafe External Calls
- Location: contracts/FeeAMM.sol : burn
- Mechanism: The function performs IERC20(userToken).transfer and IERC20(validatorToken).transfer to the recipient before deducting liquidity from liquidityBalances[poolId][msg.sender], reducing totalSupply[poolId], or subtracting from the pool reserves. There are no reentrancy guards (mutex, reentrancy guard library, or checks-effects-interactions ordering).
- Impact: An attacker controlling a reentrant token (ERC777, ERC1155 receiver, or malicious ERC20 with hooks) can re-enter burn (or other functions such as executeFeeSwap) from within the transfer callback while balances and reserves are still inflated, allowing multiple withdrawals of the same liquidity and draining both token reserves.

## Reentrancy Risk in Mint via Transfer-Then-Update Pattern
- Location: contracts/FeeAMM.sol : mint
- Mechanism: IERC20(validatorToken).transferFrom(msg.sender, address(this), amountValidatorToken) executes before any state updates to pool.reserveValidatorToken, totalSupply[poolId], or liquidityBalances[poolId][to]. No reentrancy protection exists.
- Impact: A malicious validatorToken can re-enter mint (or executeFeeSwap/rebalanceSwap) during the transferFrom, observing stale reserves and totalSupply and minting liquidity or performing swaps that would otherwise be impossible, leading to theft of validator tokens or inflation of LP shares.

## Missing Input Validation Allows Zero-Amount Operations
- Location: contracts/FeeAMM.sol : executeFeeSwap
- Mechanism: The function accepts amountIn == 0 with no explicit check (only the later _requireU128 and reserve check), computes amountOut = 0, performs a zero transferFrom/transfer, and emits an event.
- Impact: An attacker can repeatedly invoke the function at no cost to generate spurious FeeSwap events, potentially interfering with off-chain indexers, monitoring systems, or validator payment flows that rely on event integrity.

## Integer Overflow in Rebalance Amount Calculation (Pre-0.8 Arithmetic)
- Location: contracts/FeeAMM.sol : rebalanceSwap
- Mechanism: amountIn = (amountOut * N) / SCALE + 1 is computed with plain uint256 multiplication before any bounds check or _requireU128; under Solidity 0.7.x this silently wraps on overflow when amountOut > type(uint256).max / N.
- Impact: An attacker supplying a sufficiently large amountOut can cause amountIn to wrap to a tiny value, pass the subsequent uint128 check, and drain userToken reserves while only transferring a wrapped (near-zero) amount of validatorToken.

## First Mint Creates Asymmetric Reserves Without User-Token Deposit
- Location: contracts/FeeAMM.sol : mint
- Mechanism: On initial pool creation the code only transfers and records amountValidatorToken into reserveValidatorToken while leaving reserveUserToken == 0; the minted liquidity is derived solely from the validator side (amountValidatorToken/2 – MIN_LIQUIDITY).
- Impact: An attacker that is the first minter can later burn the minted liquidity to withdraw the entire validatorToken amount while the pool still holds zero userToken, or front-run subsequent swaps to extract value from the one-sided reserve imbalance.
