# Audit: 2024-01-init-capital-invitational

I have both reports in full, so I can merge directly. Here is my analysis of the overlap before writing the merged report:

- **A1 ↔ B1** (LSD oracle setters), **A2 ↔ B2** (updateOrder), **A3 ↔ B3** (fillOrder swap) are clean one-to-one matches → consensus.
- **A5** is a single combined finding that explicitly covers *both* the `LendingPool.mint/burn` delta pattern (**= B4**) and the `PosManager.addCollateral` pattern (**= B5**). So A5 splits into two consensus findings, preserving B's more specific `mintTo`/`burnTo` and `collateralize` entrypoint detail.
- **A4** (`InitCore.callback` ETH theft) has no counterpart in B → Reviewer A only.
- No finding is unique to B.

---

# Merged Security Audit Report

## Consensus findings

## Missing access control on `LsdApi3OracleReader` price-config setters
*(consensus)*
- Location: `contracts/oracle/LsdApi3OracleReader.sol` : `setDataFeedIds`, `setQuoteTokens`, `setMaxStaleTimes`
- Mechanism: In the sibling `Api3OracleReader`, every config setter carries the `onlyGovernor` modifier. In `LsdApi3OracleReader` only `setApi3OracleReader` is protected — `setDataFeedIds`, `setQuoteTokens`, and `setMaxStaleTimes` are declared plain `external` with no role check. These three writes fully control how `getPrice_e36` derives a token's USD price: it reads `dataFeedInfos[_token].dataFeedId` (the API3 exchange-rate feed), `.quoteToken` (the token whose `getPrice_e36` is multiplied in), and `.maxStaleTime` (the freshness guard).
- Impact: Any unprivileged address can repoint an LSD token's exchange-rate feed to one it controls, switch the `quoteToken` to an arbitrarily-priced token, and raise `maxStaleTime` to disable staleness protection. Since this oracle feeds `InitOracle` → `getCollateralCreditCurrent_e36` / `getBorrowCreditCurrent_e36`, an attacker can overborrow against inflated collateral, avoid liquidation with deflated debt pricing, or trigger unfair liquidations to drain lending pools. Precondition: the affected token is configured to use `LsdApi3OracleReader`.

## `MarginTradingHook.updateOrder` lets anyone modify another user's order
*(consensus)*
- Location: `contracts/hook/MarginTradingHook.sol` : `updateOrder`
- Mechanism: `cancelOrder` verifies `order.initPosId == initPosId` (the order belongs to the caller's position), but `updateOrder` omits this check. It only requires that the caller owns *some* position (`initPosId = initPosIds[msg.sender][_posId]; _require(initPosId != 0, ...)`) and then writes `order.triggerPrice_e36`, `order.limitPrice_e36`, `order.collAmt`, and `order.tokenOut` of the order identified solely by the attacker-supplied `_orderId`. The `_collAmt <= collAmt` bound is evaluated against the *attacker's* position collateral, not the victim's, and `tokenOut` is not validated against the victim position's base/quote assets at all (unlike `_createOrder`).
- Impact: An attacker holding any trivial position can overwrite any victim's active stop-loss/take-profit order — setting `limitPrice_e36`/`triggerPrice_e36` to be immediately fillable at attacker-chosen pricing, an arbitrary size, and even `tokenOut` to a fake ERC20. They (or a colluding filler) can then `fillOrder` the modified order, repay only the proportional debt, and receive the victim's collateral — theft of the victim's position equity. Precondition: the victim has an active margin order.

## `fillOrder` swaps repay-amount and repay-shares
*(consensus)*
- Location: `contracts/hook/MarginTradingHook.sol` : `_calculateRepaySize` / `_calculateFillOrderInfo` / `fillOrder` (mirrored in `contracts/helper/MarginTradingLens.sol` `_calculateRepaySize` / `_fillOrder`)
- Mechanism: `_calculateRepaySize` is declared `returns (uint repayAmt, uint repayShares)`; its body sets local `repayShares = totalDebtShares * collAmt / totalCollAmt` (a *share* count) and `repayAmt = debtShareToAmtCurrent(repayShares)` (an *underlying amount*). Because Solidity returns named values in *declaration* order, the tuple returned is `(amount, shares)`. The callers (`_calculateFillOrderInfo` / `fillOrder`) destructure it as `(repayShares, repayAmt) = _calculateRepaySize(...)`, so the variable named `repayShares` ends up holding the underlying *amount* and `repayAmt` holds the *share count*. In `fillOrder` this makes `IERC20(borrToken).safeTransferFrom(msg.sender, address(this), repayAmt)` pull in a token quantity equal to the *share count* (far too little), while `IInitCore(CORE).repay(borrPool, repayShares, ...)` passes the *underlying amount* as the `shares` argument; Core's `_repay` then computes `amtToRepay = debtShareToAmtCurrent(min(amount, posDebtShares))`, far exceeding the tokens the hook actually received.
- Impact: Once interest accrues and the debt amount diverges from debt shares, `fillOrder` reverts because the hook holds far fewer borrow tokens than Core tries to pull — bricking stop-loss/take-profit execution. Where the swapped values happen not to revert (or the hook holds spare borrow-token balance a filler can consume), repayment and the executor payout are accounted against the wrong unit, corrupting position debt/collateral. The view helper `MarginTradingLens.getFillOrderInfoCurrent` also returns the shares value in its `repayAmt` slot, feeding integrators/fillers wrong fill data. Precondition: an active order and any non-1:1 debt-share exchange rate.

## Unaccounted pool balances stealable through public `mint`/`burn`
*(consensus)*
- Location: `contracts/core/InitCore.sol` : `mintTo` / `burnTo`; `contracts/lending_pool/LendingPool.sol` : `mint` / `burn`
- Mechanism: `LendingPool.mint` mints shares from `IERC20(underlyingToken).balanceOf(pool) - cash`, and `LendingPool.burn` burns all pool shares held by the pool contract. `InitCore` exposes `mintTo` and `burnTo` publicly with arbitrary receivers, so the caller need not be the account that supplied the underlying tokens or pool shares. The protocol relies on mint-then-collateralize (and decollateralize-then-burn) being executed atomically inside a single `core.multicall`; the shipped hooks always batch atomically, but the credit is attacker-claimable whenever a gap exists.
- Impact: Any underlying accidentally or non-atomically transferred to a pool can be claimed by an attacker via `mintTo`; any pool shares sent to the pool — including a direct decollateralize-to-pool step done without an atomic `burn` — can be redeemed by an attacker via `burnTo`. Precondition: unaccounted underlying or pool shares are present at the `LendingPool` address.

## Unaccounted collateral shares assignable to an attacker's position
*(consensus)*
- Location: `contracts/core/InitCore.sol` : `collateralize`; `contracts/core/PosManager.sol` : `addCollateral`
- Mechanism: `PosManager.addCollateral` credits the caller's position with `IERC20(_pool).balanceOf(address(this)) - __collBalances[_pool]`. The `collateralize` entrypoint is public for any authorized position owner (`onlyAuthorized` over *their own* posId) and does not bind the newly observed pool-share balance to the depositor that caused it. As with mint/burn, safety depends on mint-then-collateralize being atomic inside a single `multicall`.
- Impact: If pool shares are minted or transferred to `PosManager` without an atomic `collateralize` call, an attacker can call `collateralize` for their own position and receive the collateral credit — stealing another user's pending collateral and increasing the attacker's borrowing power. Precondition: unaccounted pool shares are present at `PosManager`.

## Additional findings (single-reviewer)

## `InitCore.callback` can forward arbitrary ETH from the core's balance to any address
*(Reviewer A only)*
- Location: `contracts/core/InitCore.sol` : `callback`
- Mechanism: `callback(address _to, uint _value, bytes _data)` is `public payable` with no access control and no `nonReentrant`, and executes `ICallbackReceiver(_to).coreCallback{value: _value}(msg.sender, _data)`. `_value` is caller-controlled and is *not* bounded by `msg.value`, so it is paid out of the contract's existing ETH balance. The core sits behind `TransparentUpgradeableProxyReceiveETH`, whose `receive()` accepts ETH, and `multicall` is `payable`, so ETH can accumulate in the core (e.g., a user over-funding a payable multicall, or any direct transfer).
- Impact: Any attacker can call `callback(attackerContract, address(core).balance, "")` and have the core send its entire ETH balance to a contract they control (whose `coreCallback` they implement). Any ETH ever held by the core is stealable by an unprivileged caller.

---

*Merge notes:* No findings were unique to Reviewer B. Reviewer A's single combined "idle-balance attribution" finding was split into the two consensus findings above (`mint`/`burn` and `collateralize`/`addCollateral`) to match Reviewer B's more specific entrypoint breakdown (`mintTo`/`burnTo`, `collateralize`) while preserving Reviewer A's note that the shipped hooks batch these steps atomically, containing the risk to non-atomic integrations.

