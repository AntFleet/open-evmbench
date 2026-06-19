# Audit: 2024-01-init-capital-invitational

## Underwater Liquidation Incentive Returns Zero
- Location: `contracts/core/LiqIncentiveCalculator.sol` : `getLiqIncentiveMultiplier_e18`
- Mechanism: The function explicitly returns `0` when the position's health factor is exactly `0` (`if (_healthFactor_e18 == 0) return 0;`). This was likely added to prevent a division-by-zero error in the subsequent incentive calculation `(ONE_E18 * ONE_E18) / _healthFactor_e18`. However, returning a multiplier of `0` means the calculated `repayAmtWithLiqIncentive` in `InitCore.liquidate` becomes `0`, resulting in the liquidator receiving `0` collateral shares for repaying the bad debt.
- Impact: Completely underwater positions (health factor == 0) cannot be liquidated profitably. Liquidators will refuse to repay the debt since they receive no collateral in return, leaving the protocol with unrecoverable bad debt. The function should instead return the `maxLiqIncentiveMultiplier_e18` (or at least the minimum floor) to incentivize liquidators to clear bad debt.

## Critical Oracle Mispricing for USDY Token
- Location: `contracts/oracle/usdy/UsdyOracleReader.sol` : `getPrice_e36`
- Mechanism: The oracle fetches the USD price from `IRWADynamicOracle` (which is scaled to 1e18) and blindly multiplies it by `ONE_E18` (`1e18`). Unlike the other oracle readers (API3, Pyth) which correctly adjust for the token's decimals to return the price of **1 wei** of the token scaled by 1e36, this implementation fails to divide by `10^decimals`. For an 18-decimal token like USDY, 1 wei should be priced at `1e18` in 1e36 precision, but this function returns `1e36`.
- Impact: The protocol overvalues USDY collateral by a factor of `1e18`. An attacker can deposit a minuscule amount of USDY (e.g., 1 wei) and borrow an effectively infinite amount of other assets, completely draining the lending pools.

## Order Status Storage Update Omission
- Location: `contracts/hook/MarginTradingHook.sol` : `fillOrder`
- Mechanism: When `fillOrder` detects that the target position's collateral is empty, it attempts to cancel the order by setting `order.status = OrderStatus.Cancelled;`. However, `order` is a local `memory` copy of the struct fetched from `__orders[_orderId]`. The code fails to write this cancelled status back to the `__orders` storage mapping.
- Impact: The order remains permanently "Active" in storage. Any user can repeatedly call `fillOrder` on this orphaned order ID, and while it will safely early-return, it leaves the protocol state inconsistent and wastes gas. More importantly, if the position is later re-funded with collateral, this "cancelled" order could unexpectedly execute.
