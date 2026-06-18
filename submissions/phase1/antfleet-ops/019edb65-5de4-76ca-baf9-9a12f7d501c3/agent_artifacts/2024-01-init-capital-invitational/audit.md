# Audit: 2024-01-init-capital-invitational

## Order not cancelled when position has no collateral
- Location: `contracts/hook/MarginTradingHook.sol` : `fillOrder`
- Mechanism: The `fillOrder` function reads `Order memory order = __orders[_orderId]`. If the position has zero collateral, it sets `order.status = OrderStatus.Cancelled` on the memory copy and returns, but never writes back to storage. The order remains in `Active` state.
- Impact: An attacker can repeatedly call `fillOrder` on an order whose underlying position has been emptied, each time emitting a `CancelOrder` event but leaving the order active. If the position later receives collateral, the order can be filled unexpectedly at a potentially stale price, leading to loss of funds for the order creator.

## DoS and premature revert in fillOrder due to uncapped collateral amount
- Location: `contracts/hook/MarginTradingHook.sol` : `fillOrder`
- Mechanism: `_calculateRepaySize` caps the order’s `collAmt` to the position’s available collateral, but `fillOrder` passes the **original** `order.collAmt` to `decollateralize`. If the available collateral has dropped below the order’s `collAmt` (e.g. after a partial liquidation), the `decollateralize` call will try to withdraw more than the position holds, causing a revert.
- Impact: The order becomes unfillable even though a partial fill is mathematically possible. This can be exploited to freeze a legitimate order, forcing the owner to cancel and re-create it, or to prevent its execution entirely.

## Missing reentrancy protection in MarginTradingHook
- Location: `contracts/hook/MarginTradingHook.sol` : all externally callable functions (`openPos`, `increasePos`, `reducePos`, `addCollateral`, `removeCollateral`, `repayDebt`, `fillOrder`, `cancelOrder`, etc.)
- Mechanism: The hook does not inherit `ReentrancyGuard` or use a `nonReentrant` modifier. Functions like `fillOrder` transfer tokens to a user‑supplied `recipient` and later call `InitCore` functions that are themselves `nonReentrant`. If any whitelisted token is later upgraded to an ERC‑777 or otherwise introduces a callback on transfer, an attacker can re‑enter the hook and manipulate state (e.g., double‑fill an order, bypass health checks).
- Impact: In the worst case, an attacker can drain funds by re‑entering during a token transfer and repeating the order’s state changes before the first call finishes. Although current tokens are assumed safe, the lack of a guard is a latent vulnerability that could be exploited if the token set changes.
