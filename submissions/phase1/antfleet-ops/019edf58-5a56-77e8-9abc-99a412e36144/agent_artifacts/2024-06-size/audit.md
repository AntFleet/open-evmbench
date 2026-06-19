# Audit: 2024-06-size

## Borrow aToken cap bypass via multicall

- Location: `src/libraries/Multicall.sol` : `multicall` (and `src/libraries/actions/Deposit.sol` : `executeDeposit`)
- Mechanism: During a multicall, `executeDeposit` skips `validateBorrowATokenCap()` when `state.data.isMulticall` is true. The post-multicall guard `validateBorrowATokenIncreaseLteDebtTokenDecrease` is intended to replace that check, but it compares `state.data.borrowAToken.balanceOf(address(this))` (the contract's own held balance of repaid/unclaimed tokens) against the cap — not `totalSupply()`. A user deposit increases `totalSupply()` (minting borrowATokens to the depositor) but does **not** change `balanceOf(address(this))`. Therefore any `deposit` of borrow tokens executed inside a `multicall` (even a single-element multicall) is never caught by either the skipped per-call cap check or the post-multicall net-increase check, allowing `totalSupply()` to exceed `borrowATokenCap` without reversion.
- Impact: An attacker can deposit an arbitrary amount of borrow tokens beyond the protocol's configured `borrowATokenCap` by wrapping the `deposit` call in a `multicall`. This defeats the cap risk parameter, unbounding the protocol's exposure to the Aave variable pool and circumventing admin-configured supply limits.
