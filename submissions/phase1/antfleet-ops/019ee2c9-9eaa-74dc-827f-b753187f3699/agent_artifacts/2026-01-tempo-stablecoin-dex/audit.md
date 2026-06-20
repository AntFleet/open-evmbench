# Audit: 2026-01-tempo-stablecoin-dex

## Unrestricted emergency withdrawal lets any user drain the DEX
- Location: `contracts/StablecoinDEX.sol:372-392` (`_processWithdrawal`, `emergencyWithdraw`)
- Mechanism: `emergencyWithdraw()` is externally callable by anyone and forwards directly into `_processWithdrawal()` with no authorization or balance check. `_processWithdrawal()` then performs both `balances[user][token] -= amount` and `totalDeposits[token] -= amount` inside `unchecked`, so a caller with zero balance underflows into a huge synthetic balance instead of reverting. After corrupting accounting, the function transfers `amount` of `token` from the contract to the caller.
- Impact: Any attacker can withdraw arbitrary amounts of any token held by the DEX, including other users’ deposits and assets backing open orders, until the contract’s token balance is exhausted.

## Anyone can cancel any maker’s order
- Location: `contracts/StablecoinDEX.sol:258-262` (`cancel`)
- Mechanism: `cancel()` only checks that `order.maker != address(0)` and then calls `_cancelOrder()`; it never verifies `msg.sender == order.maker`. The declared `Unauthorized` error is never used. As a result, order ownership is ignored on the cancellation path.
- Impact: Any account can delete any live order, grief market makers, force liquidity off-book, and deny takers access to intended liquidity.

## Deposit/withdraw accounting is unsafe for fee-on-transfer or non-standard tokens
- Location: `contracts/StablecoinDEX.sol:163-171` (`deposit`), `179-186` (`withdraw`)
- Mechanism: `deposit()` credits `balances[msg.sender][token] += amount` purely from the user-supplied `amount`, without checking how many tokens the contract actually received. `withdraw()` likewise assumes sending `amount` costs the contract exactly `amount`. For tokens with transfer fees, burns, rebases, or policy-based deductions, internal balances diverge from real reserves. An attacker can deposit a token that transfers less than requested, receive full internal credit, and later extract the shortfall from the contract.
- Impact: The DEX can become insolvent for that token. Attackers can create phantom balances, withdraw more than was actually deposited, and shift the loss onto later depositors or cause honest withdrawals and settlements for that token to fail.

No additional genuine security issues stood out in `MockTIP20.sol`.

