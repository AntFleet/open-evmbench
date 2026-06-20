# Audit: 2026-01-tempo-feeamm

## Unchecked ERC20 transfers allow unpaid swaps and unbacked liquidity
- Location: `contracts/FeeAMM.sol` : `executeFeeSwap`, `rebalanceSwap`, `mint`, `burn`
- Mechanism: The contract calls `IERC20.transfer` and `IERC20.transferFrom` but never checks the returned `bool`, and it updates reserves from the requested amount rather than the actual token balance delta. In `executeFeeSwap`, a `userToken` that returns `false` or transfers less than `amountIn` still causes validator tokens to be paid out. In `rebalanceSwap`, the pool sends `userToken` after crediting `validatorToken` reserves even if `transferFrom` failed or underpaid. In `mint`, LP shares can be minted even when the validator token was not actually received.
- Impact: If a pool contains a false-returning, fee-on-transfer, or otherwise non-standard token, an attacker can receive output tokens without paying the input amount, mint unbacked liquidity, or corrupt reserves and drain the opposite token.

## Burn is reentrant before LP balances are debited
- Location: `contracts/FeeAMM.sol` : `burn`
- Mechanism: `burn` calculates withdrawal amounts, then calls `IERC20(userToken).transfer` and `IERC20(validatorToken).transfer` before reducing `liquidityBalances`, `totalSupply`, and pool reserves. A malicious or hook-capable token can reenter `burn` during either token transfer while the caller’s liquidity balance and pool reserves still reflect the pre-burn state.
- Impact: The same LP position can be burned repeatedly in one transaction, withdrawing more than its proportional share and potentially draining pool reserves. Because this is Solidity 0.7.x, repeated post-reentrancy subtractions can also underflow and corrupt pool accounting.

## Reserve additions can overflow and corrupt pool accounting
- Location: `contracts/FeeAMM.sol` : `executeFeeSwap`, `mint`
- Mechanism: The contract is compiled under Solidity `<0.8.0`, so arithmetic does not revert on overflow. `_requireU128` checks only the incoming amount, not whether `pool.reserveUserToken + amountIn` or `pool.reserveValidatorToken + amountValidatorToken` fits in `uint128`. `rebalanceSwap` has an explicit overflow check for its validator reserve addition, but the other reserve additions do not.
- Impact: A large swap or mint can wrap recorded reserves to a smaller value, making later mint, burn, and swap calculations operate on false reserve data. This can lock funds, underpay LPs, or make the pool insolvent from its own accounting perspective.

## Fixed raw-unit pricing can drain misconfigured or depegged pools
- Location: `contracts/FeeAMM.sol` : `executeFeeSwap`, `rebalanceSwap`
- Mechanism: Swap rates are computed directly from raw token units: `amountIn * M / SCALE` and `amountOut * N / SCALE`. The contract does not normalize token decimals, enforce a whitelist, or verify that both assets are actually equivalent USD-denominated units.
- Impact: If liquidity is provided for tokens with different decimals, different denominations, or a broken/depegged token, an attacker can swap the overvalued raw-unit side against the undervalued reserve and drain LP funds at the contract’s fixed rate.

