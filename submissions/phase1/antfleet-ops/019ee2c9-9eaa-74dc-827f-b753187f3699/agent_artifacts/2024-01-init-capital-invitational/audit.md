# Audit: 2024-01-init-capital-invitational

## Public Oracle Reconfiguration
- Location: `contracts/oracle/LsdApi3OracleReader.sol : setDataFeedIds`, `setQuoteTokens`, `setMaxStaleTimes`
- Mechanism: These three setter functions are externally callable but missing the `onlyGovernor` check that protects the rest of the oracle configuration surface. Any address can replace the API3 feed ID, swap the quote asset used in the LSD exchange-rate conversion, or relax/tighten staleness bounds. `getPrice_e36()` then trusts this attacker-controlled configuration when producing protocol prices.
- Impact: An attacker can arbitrarily distort collateral or debt prices, enabling undercollateralized borrowing, forced liquidations, bad debt, or protocol-wide DoS.

## Any User Can Rewrite Another User’s Live Margin Order
- Location: `contracts/hook/MarginTradingHook.sol : updateOrder`
- Mechanism: `updateOrder()` checks only that the target order is `Active`; it never verifies that `order.initPosId` belongs to `initPosIds[msg.sender][_posId]`. The collateral-size check is performed against the caller’s own position, not the order owner’s position, and `_tokenOut` is not revalidated against the position’s base/quote assets. As a result, any user with any valid margin position can overwrite another user’s order parameters and payout asset.
- Impact: An attacker can modify a victim’s stop-loss/take-profit into attacker-chosen terms, make it immediately fillable, and then execute it to acquire the victim’s collateral at an artificial discount while paying the victim a minimized amount.

## Empty Positions Do Not Actually Cancel Orders
- Location: `contracts/hook/MarginTradingHook.sol : fillOrder`
- Mechanism: In the zero-collateral branch, the function loads `Order memory order = __orders[_orderId]`, sets `order.status = OrderStatus.Cancelled`, emits `CancelOrder`, and returns. Because the status write is made only to memory, storage `__orders[_orderId]` remains `Active`. The order therefore survives on-chain even after the contract signals cancellation.
- Impact: A user can believe an old order was cancelled when the position was empty, then later reuse the same position and have that stale order unexpectedly filled against newly added collateral.

## Ambient-Balance Accounting Lets Third Parties Steal Staged Deposits and Withdrawals
- Location: `contracts/core/InitCore.sol : mintTo`, `burnTo`, `collateralize`
- Mechanism: These public entrypoints rely on downstream functions that credit or redeem based on contract-wide ambient balances instead of caller-scoped accounting: `LendingPool.mint()` mints against `balanceOf(pool) - cash`, `LendingPool.burn()` burns the entire `balanceOf(address(this))`, and `PosManager.addCollateral()` credits `balanceOf(PosManager) - __collBalances[pool]`. Once assets or pool shares have been transferred into the pool or `PosManager`, the next arbitrary caller can claim them by calling the corresponding function first.
- Impact: An attacker can front-run or sweep staged assets: mint shares for another user’s deposited underlying, burn decollateralized pool shares to themselves, or attach someone else’s pre-transferred pool shares as collateral to the attacker’s own position.

## Public Core Callback Exposes Arbitrary Privileged External Calls
- Location: `contracts/core/InitCore.sol : callback`
- Mechanism: `callback()` is fully public, takes arbitrary `_to`, `_data`, and `_value`, and performs no authorization check. It also does not bind `_value` to `msg.value`, so it can spend ETH already sitting on the core contract. The callee sees `msg.sender == CORE`, which is a privileged identity for any integrated callback receiver that authenticates only the core address.
- Impact: Any ETH held by the core can be drained to an attacker-controlled receiver, and arbitrary users can trigger callback logic on receiver contracts as if the call came from the core.

