# Audit: 2024-01-init-capital-invitational

## Unaccrued Interest in `InitCore.liquidate` Leads to Excessive Collateral Extraction
- Location: `contracts/core/InitCore.sol` : `liquidate`
- Mechanism: During liquidation, `InitCore` computes the amount of collateral shares to transfer to the liquidator by evaluating `shares = ILendingPool(_poolOut).toShares(...)`. Unlike `toSharesCurrent()`, `toShares()` does not trigger interest accrual on `_poolOut`. Since `totalDebt` is stale (lower than the true current value), `totalAssets()` will be undervalued. Because `toShares()` computes `amt * totalSupply() / totalAssets()`, the resulting `shares` count will be artificially inflated.
- Impact: Liquidators can extract more collateral shares from the user's position than they are entitled to by executing liquidations when `_poolOut` has accumulated unaccrued interest, leading to a loss of funds for the liquidated borrower.
