# Audit: 2024-06-size

I analyzed the Size protocol contracts (an order-book credit/lending market built on Aave v3). Below are the genuine security issues I found.

## Borrow aToken cap is silently disabled inside `multicall`
- Location: `src/libraries/Multicall.sol` : `multicall` (with `src/libraries/CapsLibrary.sol` : `validateBorrowATokenIncreaseLteDebtTokenDecrease`)
- Mechanism: `deposit` deliberately skips `validateBorrowATokenCap()` when `state.data.isMulticall` is true, delegating the cap enforcement to the post-loop invariant check in `multicall`. That invariant is supposed to compare the increase in the *deposited* borrow-aToken supply against the decrease in debt, so that one may only exceed the cap in order to repay. However, the before/after snapshots are taken with `state.data.borrowAToken.balanceOf(address(this))` (the protocol contract's *own* holdings, which only reflect repaid-but-unclaimed cash) instead of `state.data.borrowAToken.totalSupply()` (the metric the cap is actually defined over and the one used by `validateBorrowATokenCap`). A user `deposit` credits the *depositor's* balance, not `address(this)`, so `borrowATokenSupplyAfter - borrowATokenSupplyBefore` is ~0 for any amount of deposits. The condition `borrowATokenSupplyIncrease > debtATokenSupplyDecrease` is therefore never satisfied, and the check passes no matter how much is deposited.
- Impact: Any user can wrap a deposit in a `multicall` to mint borrow aTokens far beyond `riskConfig.borrowATokenCap`, completely neutralizing the protocol's TVL/exposure guard (the per-call cap check is skipped, and the aggregate multicall check measures the wrong quantity). The cap becomes unenforceable in practice.

## ETH deposit credits the contract's entire balance instead of the sent amount
- Location: `src/libraries/actions/Deposit.sol` : `executeDeposit`
- Mechanism: When `msg.value > 0`, the function ignores the validated `params.amount`/`msg.value` and sets `amount = address(this).balance`, then wraps and credits that full balance to `params.to`. Any ETH that has accumulated in the contract (e.g. force-sent via `selfdestruct`, a block coinbase payment, or ETH left over from a preceding step) is swept into the depositor's `szWETH` mint. Because `deposit` is reachable through the `payable` `multicall` where `msg.value` is preserved across delegatecalls, the `msg.value`-based accounting is also unreliable (this is exactly the OZ multicall hazard the file comments reference).
- Impact: A depositor can mint deposit tokens for ETH they did not supply, capturing any stray/forced ETH balance held by the contract. The accounting should bind to the amount actually transferred in this call (`msg.value`), not the contract's aggregate balance.

## Notes on areas I checked that are *not* bugs
- The liquidation protocol-fee selection (`Liquidate.executeLiquidate`) correctly prefers the underwater fee over the overdue fee.
- `Claim` interest scaling (`credit * currentIndex / liquidityIndexAtRepayment`) is conserved against the contract's scaled holdings; it cannot over-draw.
- `liquidateWithReplacement` correctly burns the old borrower's debt before reassigning and re-minting to the (solvency-checked) replacement borrower.
- Collateral-ratio direction, self-liquidation `< PERCENT` loss gate, and the non-transferrable token access controls (owner-gated mint/burn/transfer, max allowance only for the owner) are all sound.

The first issue is the most serious (a defeated protocol-wide risk limit); the second is a real but lower-severity accounting flaw gated by the presence of stray ETH.

