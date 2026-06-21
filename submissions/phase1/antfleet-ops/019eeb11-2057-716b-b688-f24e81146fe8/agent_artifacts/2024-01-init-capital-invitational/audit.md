# Audit: 2024-01-init-capital-invitational
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Missing access control on LsdApi3OracleReader price-config setters
*(consensus, 5 of 6 reports)*
- Location: `contracts/oracle/LsdApi3OracleReader.sol` : `setDataFeedIds`, `setQuoteTokens`, `setMaxStaleTimes`
- Mechanism: Unlike `setApi3OracleReader` (and the equivalent setters in `Api3OracleReader`/`PythOracleReader`), these three setters are declared `external` with no `onlyGovernor` modifier, so any address can overwrite the data-feed id, quote token, and max-stale-time used by `getPrice_e36` (`rate_e18.toUint256().mulDiv(api3OracleReader.getPrice_e36(quoteToken), 1e18)`).
- Impact: For any token whose primary/secondary source in `InitOracle` is this reader, an attacker controls all three price inputs in a single permissionless tx: inflate collateral credit in `InitCore.getCollateralCreditCurrent_e36` to borrow against worthless collateral and drain pools, or deflate it to force-liquidate healthy positions. Direct path to total loss of funds for affected markets.
- Reviewer disagreement: none.

## fillOrder swaps repay-amount and repay-shares
*(consensus, 4 of 6 reports)*
- Location: `contracts/hook/MarginTradingHook.sol` : `_calculateRepaySize` / `_calculateFillOrderInfo` / `fillOrder` (mirrored in `contracts/helper/MarginTradingLens.sol` : `_calculateRepaySize` / `_fillOrder` / `getFillOrderInfoCurrent`)
- Mechanism: `_calculateRepaySize` is declared `returns (uint repayAmt, uint repayShares)` and its body sets `repayShares = totalDebtShares * collAmt / totalCollAmt` (share count) and `repayAmt = debtShareToAmtCurrent(repayShares)` (token amount) — tuple is `(amount, shares)`. The caller destructures in the wrong order: `(repayShares, repayAmt) = _calculateRepaySize(...)`. Thereafter `fillOrder` does `safeTransferFrom(msg.sender, this, repayAmt)` (pulls only a *share count* of tokens) and `IInitCore.repay(borrPool, repayShares, ...)` (passes the *amount* as the shares argument); `amtOut` is likewise computed from the swapped value.
- Impact: Amount and shares coincide only at 1:1 before interest accrues (masking it in tests). Once interest accrues, `repay` requires `debtShareToAmtCurrent(...)` underlying — more than the share-valued amount pulled in — so `fillOrder` reverts, making every stop-loss / take-profit order permanently unfillable (core safety feature DoS). Where it doesn't revert, debt accounting is corrupted and the recipient receives a mis-priced `amtOut`.
- Reviewer disagreement: none.

## Permissionless InitCore.callback drains contract-held ETH
*(consensus, 3 of 6 reports)*
- Location: `contracts/core/InitCore.sol` : `callback`
- Mechanism: `callback(address _to, uint _value, bytes _data)` is `public payable`, unauthenticated, not `nonReentrant`, and does not require `_value <= msg.value`. It executes `ICallbackReceiver(_to).coreCallback{value: _value}(msg.sender, _data)` with a caller-chosen `_value` drawn from the contract balance. The core sits behind a proxy with a payable `receive()`, so the address can hold ETH.
- Impact: If any ETH is ever held by the core (stray transfer, payable multicall whose subcalls don't consume `msg.value`), anyone can call `callback(attacker, address(core).balance, "")` and forward the full balance to an attacker-controlled receiver. Conditional on the core holding ETH, but a permissionless drain.
- Reviewer disagreement: opus shot 1 explicitly defended this code path, arguing that consumers reject any `_sender` that is not themselves and that "InitCore custodies no funds, so the open callback is not exploitable."

## updateOrder lets any position owner rewrite another user's margin order
*(consensus, 3 of 6 reports)*
- Location: `contracts/hook/MarginTradingHook.sol` : `updateOrder`
- Mechanism: `updateOrder` checks that `msg.sender` owns `_posId` but never checks `order.initPosId == initPosId`, and it omits the `_tokenOut == baseAsset || _tokenOut == quoteAsset` validation present in `_createOrder`. The collateral-size check is performed against the caller's own position, not the order owner's. So any user with any valid margin position can mutate any active order's trigger price, limit price, collateral size, and output token.
- Impact: An attacker rewrites a victim's active stop-loss/take-profit order to an immediately triggerable price with an attacker-controlled worthless `tokenOut`, then fills it in the same tx — repaying only the proportional victim debt while receiving the victim's collateral shares, draining the victim's equity. Precondition: victim has an active order.
- Reviewer disagreement: none.

## Unaccounted assets sent to PosManager are claimable by any position (shares and wLp NFTs)
*(consensus, 3 of 6 reports)*
- Location: `contracts/core/PosManager.sol` : `addCollateral`, `addCollateralWLp` (reachable via `InitCore.collateralize` / `collateralizeWLp`)
- Mechanism: `addCollateral` credits `IERC20(_pool).balanceOf(this) - __collBalances[_pool]` to the caller-selected `posId`, and `addCollateralWLp` credits any wLp `tokenId` PosManager already owns and that is not yet `isCollateralized` to the caller's `posId`. Neither path binds the credit to the depositor, and there is no atomic deposit+collateralize entrypoint for wLp.
- Impact: Between a victim's transfer-then-collateralize steps, an attacker calls `collateralizeWLp(attackerPosId, wLp, tokenId)` / `collateralize(attackerPosId, pool)`, passes the `onlyAuthorized` check on their own position, and the victim's freshly minted shares or wLp NFT are credited to the attacker, who can then decollateralize them out — full theft of non-atomically deposited collateral.
- Reviewer disagreement: none.

## Empty-position order cancellation only updates the memory copy
*(consensus, 2 of 6 reports)*
- Location: `contracts/hook/MarginTradingHook.sol` : `fillOrder`
- Mechanism: `fillOrder` loads `Order memory order = __orders[_orderId]`. In the empty-collateral branch it sets `order.status = OrderStatus.Cancelled` and emits `CancelOrder`, but this writes only the memory copy — `__orders[_orderId].status` stays `Active`.
- Impact: The contract emits a cancellation event while the order remains live in storage. If collateral is later added back to the same position, the supposedly cancelled order can still be filled by anyone at old terms; off-chain systems are misled. Precondition: an active order whose position temporarily has zero collateral, later reused.
- Reviewer disagreement: none.

## fillOrder marks order Filled only after external calls (reentrancy / double-fill)
*(consensus, 2 of 6 reports)*
- Location: `contracts/hook/MarginTradingHook.sol` : `fillOrder`
- Mechanism: After checking `order.status == Active`, `fillOrder` performs `safeTransferFrom` of `tokenOut`/`borrToken` and calls `CORE.repay` / `CORE.decollateralize`, and only afterward sets `__orders[_orderId].status = OrderStatus.Filled`. The hook has no `nonReentrant` guard — a CEI violation.
- Impact: If `tokenOut` or `borrToken` has a transfer callback (ERC-777-style), the filler/recipient can re-enter `fillOrder(_orderId)` while storage status is still `Active`, executing the same order repeatedly and decollateralizing far more than the owner authorized. Precondition: a callback-capable token is one of the position's assets.
- Reviewer disagreement: none.

## Pre-transferred pool underlying/shares stealable via mintTo / burnTo
*(consensus, 2 of 6 reports)*
- Location: `contracts/core/InitCore.sol` : `mintTo`, `burnTo`; `contracts/lending_pool/LendingPool.sol` : `mint`, `burn`
- Mechanism: `LendingPool.mint` mints from `balanceOf(pool) - cash` and `burn` redeems whatever pool shares sit on the pool contract; the public core wrappers let the caller choose the share/asset recipient, with no binding between the account that transferred tokens/shares in and the account that calls `mintTo`/`burnTo`.
- Impact: Underlying sent to a pool before `mintTo`, or pool shares sent before `burnTo`, can be front-run/back-run and minted/redeemed to an attacker. Atomic multicall avoids this, but the exposed non-atomic path is stealable.
- Reviewer disagreement: none.

## Minority findings

## USDY oracle missing token-decimal normalization (price overstated by 10^decimals)
*(minority, 1 of 6 reports)*
- Location: `contracts/oracle/usdy/UsdyOracleReader.sol` : `getPrice_e36`
- Mechanism: Every other reader produces a per-wei `price_e36` (e.g. `Api3OracleReader` does `price * 1e18 / 10**decimals`). `UsdyOracleReader` returns `IRWADynamicOracle.getPrice() * ONE_E18` and never divides by `10**decimals`. Since `getPrice()` is a 1e18-scaled USD price per whole token, the result is per-whole-token in 1e36, i.e. `10**18` too large for 18-decimal USDY.
- Impact: In `getCollateralCreditCurrent_e36`, `price_e36` multiplies the raw wei amount, so a $1 USDY position contributes `1e54` instead of `1e36` of credit. If USDY is enabled as collateral, a trivial USDY deposit lets an attacker borrow essentially the entire protocol — instant insolvency.
- Reviewer disagreement: none (no other report examined this reader).

## LsdApi3OracleReader staleness check underflows on future-dated updates
*(minority, 1 of 6 reports)*
*(conflicting reviews: 1 of 6 reports treated this code path's behavior as correct)*
- Location: `contracts/oracle/LsdApi3OracleReader.sol` : `getPrice_e36`
- Mechanism: The freshness check is `_require(block.timestamp - timestamp <= maxStaleTime, ...)` with no guard that `block.timestamp >= timestamp`. If the API3 feed reports a timestamp ahead of `block.timestamp` (clock skew / fresh push), the subtraction underflows and reverts under checked arithmetic — `Api3OracleReader` avoids this with an `if (block.timestamp > timestamp)` guard.
- Impact: Price reads for tokens using this reader revert whenever the upstream timestamp is in the future. `InitOracle.getPrice_e36` try/catches and drops the source, but if it is the only valid source, health/credit computations revert — temporarily blocking borrows, withdrawals, and (critically) liquidations. Availability bug.
- Reviewer disagreement: opus shot 3, while flagging the *opposite* bug in `Api3OracleReader`, characterized `LsdApi3OracleReader`'s subtract-and-revert as the stricter/correct behavior.

## Api3 staleness check skipped for future-dated timestamps
*(minority, 1 of 6 reports)*
*(conflicting reviews: 1 of 6 reports defended this code path)*
- Location: `contracts/oracle/Api3OracleReader.sol` : `getPrice_e36`
- Mechanism: The freshness check is gated by `if (block.timestamp > timestamp) { require(block.timestamp - timestamp <= maxStaleTime); }`. When the feed reports a `timestamp` greater than `block.timestamp`, the staleness requirement is bypassed entirely and the price is accepted with no other validation (unlike Pyth/Lsd readers, which subtract).
- Impact: A misbehaving or manipulated feed publishing a future timestamp evades the max-stale-time protection, letting a stale/incorrect price be used for collateral and debt valuation. Lower severity (depends on feed behavior) but a genuine missing freshness guarantee.
- Reviewer disagreement: opus shot 1 presented this exact `if (block.timestamp > timestamp)` guard as the *correct* pattern (the model of soundness it contrasted against the LSD reader's underflow), implicitly treating the future-timestamp branch as safe.

## Oracle readers accept zero prices
*(minority, 1 of 6 reports)*
- Location: `contracts/oracle/Api3OracleReader.sol`, `contracts/oracle/PythOracleReader.sol`, `contracts/oracle/LsdApi3OracleReader.sol`, `contracts/oracle/usdy/UsdyOracleReader.sol` : `getPrice_e36`
- Mechanism: The readers reject negative prices via casts but do not reject zero. If `InitOracle` has only one valid source for a token, a zero price is accepted and propagated into health calculations.
- Impact: If a borrow asset's oracle returns zero, `getBorrowCreditCurrent_e36` can value that debt at zero, making positions appear infinitely healthy and allowing borrowing up to configured caps. Precondition: a zero-valued or attacker-influenced upstream feed (or the unrestricted LSD oracle config above).
- Reviewer disagreement: none.

---

*Reconciliation: 12 distinct findings across the 6 input reports (3 opus shots: A,B,I / A,B / H,B,F,G2,C,J; 3 gpt shots: A,D,E,C / A,D,B,E,G1+G2 / A,D,F,C,G1,G2,K). All 12 are emitted above — no finding dropped.*

