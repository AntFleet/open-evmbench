# Audit: 2026-01-tempo-feeamm

## Reentrancy Vulnerability in `burn` Due to CEI Violation
- Location: `contracts/FeeAMM.sol` : `burn`
- Mechanism: The `burn` function violates the Checks-Effects-Interactions (CEI) pattern by updating critical state variables (`liquidityBalances`, `totalSupply`, and `pool` reserves) *after* executing external `IERC20.transfer` calls. Because the contract allows arbitrary ERC20 tokens to be used as `userToken` or `validatorToken`, an attacker can supply a malicious token implementation that supports transfer callbacks (such as ERC777 or an ERC20 with custom hooks). When the tokens are transferred to the `to` address, the recipient contract can re-enter the `burn` function. Since the sender's `liquidityBalances` has not yet been decremented, the re-entered call will pass the balance check and calculate the exact same withdrawal amounts.
- Impact: An attacker can recursively re-enter the `burn` function to withdraw the same liquidity shares multiple times, completely draining the pool's `userToken` and `validatorToken` reserves.

## Unchecked Return Values for ERC20 `transfer` and `transferFrom`
- Location: `contracts/FeeAMM.sol` : `executeFeeSwap`, `rebalanceSwap`, `mint`, `burn`
- Mechanism: The contract interacts with arbitrary ERC20 tokens via the `IERC20` interface but fails to check the boolean return values of `transfer` and `transferFrom` calls. Several widely used ERC20 tokens (most notably USDT) do not revert on failure but instead return `false`. The contract assumes these calls will revert on failure and proceeds to update internal accounting (reserves, liquidity balances, and total supply) regardless of whether the transfer actually succeeded.
- Impact: If a `transferFrom` call fails silently, a user can execute swaps or mint liquidity without actually depositing the required input tokens, effectively stealing output tokens or liquidity shares from the pool. If a `transfer` call fails silently, the contract will deduct reserves and burn liquidity shares without sending the underlying tokens to the user, resulting in permanent accounting drift and locked funds.
