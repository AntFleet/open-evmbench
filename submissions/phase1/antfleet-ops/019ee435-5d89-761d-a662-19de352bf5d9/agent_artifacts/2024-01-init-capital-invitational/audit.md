# Audit: 2024-01-init-capital-invitational

## Unrestricted LSD oracle configuration

- Location: `contracts/oracle/LsdApi3OracleReader.sol` : `setDataFeedIds`, `setQuoteTokens`, `setMaxStaleTimes`
- Mechanism: These three external setters are missing the `onlyGovernor` modifier. Any address can overwrite the API3 data feed id, quote token, and stale-time limit used by `getPrice_e36()`. The reader then trusts the attacker-controlled `DataFeedInfo` and returns `rate * quoteTokenPrice` as the token price.
- Impact: An attacker can manipulate prices for LSD assets using this reader. If such an asset is accepted as collateral or debt, they can inflate collateral value, deflate debt value, bypass liquidation, liquidate healthy users, or borrow against fake collateral value and drain lending pools.

## Anyone can rewrite another user’s margin order

- Location: `contracts/hook/MarginTradingHook.sol` : `updateOrder`
- Mechanism: `updateOrder()` loads `__orders[_orderId]` and only checks that the order is active. It derives `initPosId` from `msg.sender` and `_posId`, but never checks `order.initPosId == initPosId`. It also does not validate that the new `_tokenOut` is the position’s base or quote asset.
- Impact: Any user with any valid position can modify another user’s active stop-loss or take-profit order. The attacker can set attacker-favorable trigger/limit values and a worthless or malicious `tokenOut`, then fill the victim’s order and seize the victim’s collateral while paying far less than the intended consideration.

## Margin order repayment values are swapped

- Location: `contracts/hook/MarginTradingHook.sol` : `fillOrder`, `_calculateFillOrderInfo`, `_calculateRepaySize`
- Mechanism: `_calculateRepaySize()` declares returns as `(uint repayAmt, uint repayShares)`, but callers destructure it as `(repayShares, repayAmt)`. `fillOrder()` therefore uses debt shares where it expects token amounts, and passes a token amount where `IInitCore.repay()` expects debt shares. Once interest accrues and debt-share price diverges from 1:1, the fill path calculates and funds the wrong repayment.
- Impact: Stop-loss and take-profit orders can become unfillable after debt accrues. Users relying on these orders for risk management can remain exposed during adverse price moves and be liquidated instead of having their margin position closed by keepers.

## Margin orders can be reentered before being marked filled

- Location: `contracts/hook/MarginTradingHook.sol` : `fillOrder`
- Mechanism: `fillOrder()` marks `__orders[_orderId].status = OrderStatus.Filled` only after external token transfers and core calls. During `safeTransferFrom()` of `borrToken` or `order.tokenOut`, or during downstream external calls, a callback-capable/malicious token can reenter `fillOrder()` for the same `_orderId` while it is still `Active`.
- Impact: The same order can be filled multiple times in one transaction, allowing a filler to remove more collateral than the order owner authorized. Combined with the unrestricted `updateOrder()` bug, an attacker can set a malicious `tokenOut`, reenter, and drain victim collateral repeatedly.

## Public callback can spend native ETH held by Core

- Location: `contracts/core/InitCore.sol` : `callback`
- Mechanism: `callback()` is public and sends `_value` native ETH from the Core contract to arbitrary `_to`, but it does not require `_value == msg.value` or otherwise account for the caller’s deposited value. Any caller can choose an attacker-controlled `ICallbackReceiver` and request ETH already sitting in the Core/proxy balance.
- Impact: Any native ETH accidentally or forcibly held by the Core proxy can be drained by an attacker. This does not directly drain ERC20 lending-pool assets, but it makes all native-token balance on Core publicly stealable.

