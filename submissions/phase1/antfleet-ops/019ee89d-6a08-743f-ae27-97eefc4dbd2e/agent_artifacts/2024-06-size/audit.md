# Audit: 2024-06-size

## Borrow aToken cap can be bypassed via multicall
- Location: src/libraries/Multicall.sol : `multicall` (together with src/libraries/actions/Deposit.sol : `executeDeposit`)
- Mechanism: `executeDeposit` deliberately skips `validateBorrowATokenCap()` whenever `state.data.isMulticall` is true ("users must be able to deposit more tokens to repay debt"). The compensating post-batch guard in `Multicall.multicall` is supposed to re-enforce the cap through `CapsLibrary.validateBorrowATokenIncreaseLteDebtTokenDecrease`, whose cap branch is `if (borrowATokenSupplyAfter > state.riskConfig.borrowATokenCap)`. But `multicall` feeds that function `state.data.borrowAToken.balanceOf(address(this))` — the Size contract's own transient holdings — as the "supply", instead of `borrowAToken.totalSupply()`. A deposit mints szaUSDC to `params.to` (the user) via `mintScaled`, never to the Size contract, so `balanceOf(address(this))` is unchanged by deposits; `borrowATokenSupplyAfter` stays near zero, the cap branch is never entered, and `borrowATokenSupplyIncrease` is always 0. A bare `multicall([deposit(borrowToken, hugeAmount, attacker)])` therefore deposits past the cap and the over-cap supply persists permanently.
- Impact: Any user can mint szaUSDC beyond `riskConfig.borrowATokenCap`, defeating the protocol's intended exposure limit to the Aave variable pool.

## Deposit wraps the contract's entire ETH balance, enabling theft of stranded ETH
- Location: src/libraries/actions/Deposit.sol : `executeDeposit`
- Mechanism: When `msg.value > 0`, `executeDeposit` sets `amount = address(this).balance` and wraps the *entire* contract ETH balance into WETH, then credits all of it to `params.to`, while `validateDeposit` only requires `msg.value == params.amount`. Per `ISize`, every external action is `payable`, but only `deposit`/`multicall` consume `msg.value`; ETH mistakenly attached to any other payable call (`repay`, `claim`, `liquidate`, `compensate`, …) stays in the contract. An attacker can then call `deposit({token: weth, amount: 1, to: attacker})` with `msg.value == 1`, causing `amount = address(this).balance` (stranded ETH + 1) to be wrapped and credited to the attacker, who withdraws it.
- Impact: An attacker can sweep any ETH stranded in the Size contract (collateral credited for free, then withdrawn), causing loss of those funds.

