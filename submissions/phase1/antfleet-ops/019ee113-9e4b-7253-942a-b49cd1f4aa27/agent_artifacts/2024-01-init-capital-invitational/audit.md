# Audit: 2024-01-init-capital-invitational

# Security Audit Findings

## fillOrder enforces health, blocking stop-loss on underwater positions
- Location: `contracts/hook/MarginTradingHook.sol` : `fillOrder`
- Mechanism: `fillOrder` calls `IInitCore(CORE).decollateralize(...)` to transfer collateral to the filler. `decollateralize` carries the `ensurePositionHealth` modifier, which reverts unless `getPosHealthCurrent_e18 >= 1e18`. For a partial stop-loss order on a position that is already unhealthy and remains unhealthy after the proportional debt repay + collateral removal (or for a take-profit that nonetheless pushes health below 1e18), the entire `fillOrder` reverts even though `_validateTriggerPrice` passed. Unlike `liquidate`, which uses `removeCollateralTo` directly and bypasses the health check (and uses `_ensurePosHealthAfterLiq` as a soft cap), `fillOrder` has no such bypass and is not wrapped in `multicall` (so `isMulticallTx` is false). The user's repay transfer and tokenOut transfer occur before the revert point, but the whole tx reverts so funds are safe — however the order is effectively unfillable in this state.
- Impact: Stop-loss orders cannot protect positions that are already underwater; liquidators (who can call `liquidate` directly) capture the collateral instead of the stop-loss filler, and position owners bear additional losses they explicitly tried to limit.

## Rebase helper uses entire balance, allowing donation/inflation of collateral
- Location: `contracts/helper/rebase_helper/mUSDUSDYHelper.sol` : `wrap`, `unwrap`
- Mechanism: `wrap` does `uint balance = IERC20(REBASE_TOKEN).balanceOf(address(this)); IMUSD(REBASE_TOKEN).unwrap(balance);` and transfers the resulting `YIELD_BEARING_TOKEN` balance to the caller. `unwrap` does the symmetric `balanceOf(YIELD_BEARING_TOKEN)` → `wrap` → transfer all rebase shares. In `MoneyMarketHook._handleDeposit` the hook transfers `amt` rebase tokens from the user and then calls `helper.wrap(pool)`; whatever pre-existing rebase tokens sit in the helper are also unwrapped and credited to the pool as if they belonged to this depositor. The same path lets an attacker who donated rebase tokens inflate the next user's minted pool shares / collateral.
- Impact: A donor can grief suppliers by forcing extra share inflation (and can collude with a depositor to mint more collateral than they paid for, then borrow against it). It also breaks the implicit invariant that `amt` parameter corresponds to minted shares.

## Oracle division-by-zero when primary source returns 0 with secondary configured
- Location: `contracts/oracle/InitOracle.sol
