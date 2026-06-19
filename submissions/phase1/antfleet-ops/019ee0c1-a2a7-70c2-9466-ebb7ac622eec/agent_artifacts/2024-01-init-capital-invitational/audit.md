# Audit: 2024-01-init-capital-invitational

I found the following genuine vulnerabilities.

## Unprotected LSD oracle configuration lets anyone rewrite prices
- Location: `contracts/oracle/LsdApi3OracleReader.sol` : `setDataFeedIds`, `setQuoteTokens`, `setMaxStaleTimes`
- Mechanism: These three oracle-configuration setters are `external` and lack `onlyGovernor`, unlike `setApi3OracleReader`. Any address can change a token’s `dataFeedId`, `quoteToken`, and stale-time configuration. `getPrice_e36()` then trusts those attacker-controlled fields to read an API3 feed and multiply it by the attacker-selected quote token price.
- Impact: An attacker can manipulate or disable oracle pricing for any token using this reader. If the reader is used for collateral/debt pricing, this can enable over-borrowing, wrongful liquidations, or system-wide DoS for affected markets.

## Anyone with a position can rewrite any margin order
- Location: `contracts/hook/MarginTradingHook.sol` : `updateOrder`
- Mechanism: `updateOrder()` loads `__orders[_orderId]` but never checks that `order.initPosId == initPosId` for the caller’s `_posId`. It only verifies that the caller has some position. It also fails to validate that the new `_tokenOut` is one of the margin position’s base/quote assets. The collateral-size check is performed against the attacker’s position, not the order owner’s position.
- Impact: An attacker can create a minimal position, update a victim’s active stop-loss/take-profit order, set malicious trigger/limit values and even a worthless attacker-controlled `tokenOut`, then fill the order. The attacker repays some of the victim’s debt and receives the victim’s collateral shares, while the victim receives worthless or badly mispriced tokens.

## Margin order repayment units are swapped
- Location: `contracts/hook/MarginTradingHook.sol` : `_calculateRepaySize`, `_calculateFillOrderInfo`, `fillOrder`
- Mechanism: `_calculateRepaySize()` declares returns as `(uint repayAmt, uint repayShares)`, but callers destructure it as `(repayShares, repayAmt)`. As a result, `fillOrder()` treats debt shares as token amounts and token amounts as debt shares. It transfers only the share count of borrow tokens from the filler, but calls `IInitCore.repay()` using the token amount as the share amount.
- Impact: Once interest accrues and debt amount per share diverges from 1:1, legitimate stop-loss/take-profit order fills can revert or settle using incorrect amounts. Protective orders become unreliable exactly when users need them, exposing positions to liquidation instead of the intended automated close.

## Public callback can drain native ETH held by Core
- Location: `contracts/core/InitCore.sol` : `callback`
- Mechanism: `callback(address _to, uint _value, bytes _data)` is fully public and only rejects `_to == address(this)`. It does not require `_value == msg.value` and does not authorize the caller. Because the proxy variant can receive ETH, any ETH balance held by the Core proxy can be forwarded by an arbitrary caller to an attacker-controlled `ICallbackReceiver`.
- Impact: Any native ETH accidentally or intentionally sent to the Core proxy can be stolen by calling `callback(attackerReceiver, amount, data)`.

## Delta-balance mint and burn flows are front-runnable
- Location: `contracts/core/InitCore.sol` : `mintTo`, `burnTo`; `contracts/core/PosManager.sol` : `addCollateral`
- Mechanism: Pool minting, burning, and collateralization are based on ambient contract balances rather than caller-bound amounts. `LendingPool.mint()` mints shares for the entire underlying-token balance delta. `LendingPool.burn()` burns all pool shares currently held by the pool contract. `PosManager.addCollateral()` assigns the entire pool-share balance delta held by `PosManager` to the caller’s chosen position.
- Impact: If a user or integration performs a non-atomic transfer-then-call flow, an attacker can front-run the second step and claim the transferred assets. Examples: after a victim transfers underlying to a pool, the attacker calls `mintTo(pool, attacker)`; after a victim transfers pool shares to the pool or `PosManager`, the attacker can redeem or collateralize those shares for themselves.

