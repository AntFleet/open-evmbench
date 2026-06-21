# Audit: 2024-01-init-capital-invitational

## Unprotected LSD oracle configuration
- Location: contracts/oracle/LsdApi3OracleReader.sol : `setDataFeedIds`, `setQuoteTokens`, `setMaxStaleTimes`
- Mechanism: Unlike the sibling `Api3OracleReader`, these three configuration functions are declared `external` with no `onlyGovernor` (or any) access control, while `setApi3OracleReader` is governor-gated. Any address can overwrite a token’s `dataFeedId`, `quoteToken`, and `maxStaleTime`, which directly controls how `getPrice_e36` computes collateral/debt values.
- Impact: An attacker can point LSD tokens at arbitrary/malicious feeds, disable staleness checks, or skew quote-token linkage. If this reader is wired into `InitOracle`, the attacker can inflate collateral value, borrow against undercollateralized positions, and extract protocol funds.

## Swapped repay amount and shares in order fill
- Location: contracts/hook/MarginTradingHook.sol : `_calculateFillOrderInfo`, `fillOrder`
- Mechanism: `_calculateRepaySize` is defined to return `(repayAmt, repayShares)` (token amount first, debt shares second), but `_calculateFillOrderInfo` destructures the result as `(repayShares, repayAmt)`, reversing the two values. `fillOrder` then uses the swapped values to (1) compute `amtOut`, (2) pull borrow tokens from the filler, and (3) call `InitCore.repay` with debt shares.
- Impact: Order fills use the wrong repayment size and wrong share count. A filler can repay far less debt than intended while still receiving the decollateralized pool shares, and the order owner receives incorrect `tokenOut` amounts. This breaks the order’s economic guarantees and lets executors capture collateral at the expense of position owners.

## Missing order ownership check on update
- Location: contracts/hook/MarginTradingHook.sol : `updateOrder`
- Mechanism: `cancelOrder` correctly enforces `order.initPosId == initPosId`, but `updateOrder` only checks that the caller has some valid `initPosId` for their local `_posId`. It never verifies that the order being modified belongs to that position (`order.initPosId == initPosId`).
- Impact: Any user with any margin position can modify any active order by ID, changing `triggerPrice_e36`, `limitPrice_e36`, `collAmt`, and `tokenOut` on another user’s stop-loss/take-profit order. This enables griefing and, combined with the fill bug above, lets an attacker rewrite a victim’s order into a profitable fill for themselves.

## Wrong collateral basis when updating orders
- Location: contracts/hook/MarginTradingHook.sol : `updateOrder`
- Mechanism: When validating `_collAmt`, the function loads `marginPos` and `getCollAmt` from the caller’s `initPosId`, not from `order.initPosId` (the position the order actually references). `_createOrder` correctly checks collateral on the order’s position; `updateOrder` does not.
- Impact: An attacker can raise a victim’s order `collAmt` based on the attacker’s own collateral balance (or an unrelated pool), even when the victim’s position cannot support that size. A subsequent `fillOrder` can then decollateralize more of the victim’s position than they authorized when the order was created.

## Spot AMM reserve pricing for wLP collateral
- Location: contracts/wrapper/WLpMoeMasterChef.sol : `calculatePrice_e36`
- Mechanism: wLP collateral value is derived from instantaneous Uniswap V2–style pair reserves (`getReserves`, `kLast`, `totalSupply`) multiplied by external token prices. There is no TWAP, manipulation guard, or liquidity minimum.
- Impact: An attacker can flash-loan manipulate pool reserves before `borrow`, `liquidate`, or `liquidateWLp` pricing reads, temporarily inflating wLP collateral value, borrowing against it, and leaving bad debt when reserves normalize. This is a classic LP-oracle manipulation path against positions using wLP collateral.

## Order auto-cancel does not update storage
- Location: contracts/hook/MarginTradingHook.sol : `fillOrder`
- Mechanism: When a position has zero collateral, `fillOrder` sets `order.status = OrderStatus.Cancelled` on a memory copy of the order and returns without writing `__orders[_orderId].status`. The order remains `Active` in storage.
- Impact: Orders on empty positions can never be cleared from the active set via the intended auto-cancel path. Fillers keep retrying, events misreport cancellation, and stale orders remain fillable if collateral is re-deposited later under unintended terms (especially if combined with the `updateOrder` flaws above).

## Pyth price used without confidence validation
- Location: contracts/oracle/PythOracleReader.sol : `getPrice_e36`
- Mechanism: The reader calls `IPyth.getPriceUnsafe` and only checks `publishTime` staleness. It ignores the returned confidence interval (`conf`) and does not verify that the on-chain price update was freshly submitted in the same transaction.
- Impact: During periods of high volatility or oracle disruption, low-confidence or stale Pyth prices can be used for collateral valuation and liquidation math, allowing borrows against temporarily mispriced assets or unfair liquidations until governance intervenes.

