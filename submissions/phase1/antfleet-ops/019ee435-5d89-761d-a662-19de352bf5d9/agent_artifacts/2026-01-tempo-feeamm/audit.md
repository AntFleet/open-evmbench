# Audit: 2026-01-tempo-feeamm

## ERC-20 transfers are trusted even when no tokens are received
- Location: `contracts/FeeAMM.sol` : `executeFeeSwap`, `rebalanceSwap`, `mint`
- Mechanism: The contract calls `IERC20.transferFrom` but ignores the returned `bool` and never checks the contract’s token balance delta. In Solidity 0.7, an ERC-20 that returns `false` does not revert the transaction if the return value is ignored. The AMM then updates reserves and mints liquidity as if the full nominal amount was received. Fee-on-transfer or malicious tokens also desync accounting because reserves are credited by `amountIn` / `amountValidatorToken` rather than actual received tokens.
- Impact: An attacker can swap for real `validatorToken` without actually paying `userToken`, perform `rebalanceSwap` to withdraw `userToken` without paying `validatorToken`, or mint LP shares without depositing the expected backing tokens. This can drain the honest side of any pool that contains a token with false-returning or deflationary transfer behavior.

## Burn is reentrant before LP balances and reserves are debited
- Location: `contracts/FeeAMM.sol` : `burn`
- Mechanism: `burn` transfers `userToken` and `validatorToken` to `to` before reducing `liquidityBalances`, `totalSupply`, and pool reserves. If either token invokes attacker-controlled code during `transfer`, the attacker can reenter `burn` while their LP balance and the pool reserves still reflect the pre-burn state. Because the contract is compiled for Solidity `<0.8.0`, repeated post-reentrancy subtractions can also underflow instead of reverting.
- Impact: An LP can burn the same liquidity multiple times in one transaction and withdraw more than their pro-rata share, draining other LPs’ reserves from pools involving a callback-capable or malicious token.

## Outbound transfer failures silently corrupt accounting
- Location: `contracts/FeeAMM.sol` : `executeFeeSwap`, `rebalanceSwap`, `burn`
- Mechanism: The contract ignores the returned `bool` from outbound `IERC20.transfer` calls. Reserves and LP balances are updated as if the recipient received funds even when the token returns `false`. In `burn`, the LP balance is reduced after the unchecked transfers; in swaps, reserves are moved before/around an unchecked payout.
- Impact: Users or LPs can lose claims without receiving the owed tokens, and pool reserves can become inconsistent with actual balances. A malicious or false-returning token can cause swaps and burns to report success while withholding the payout, leaving accounting permanently wrong.

