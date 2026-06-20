# Audit: 2024-01-init-capital-invitational

## Unprotected LSD oracle configuration

- Location: `contracts/oracle/LsdApi3OracleReader.sol` : `setDataFeedIds`, `setQuoteTokens`, `setMaxStaleTimes`
- Mechanism: These configuration setters are external and lack `onlyGovernor`, unlike `setApi3OracleReader`. Any address can rewrite a token’s `dataFeedId`, `quoteToken`, and stale-time limit. `getPrice_e36()` then uses the attacker-controlled feed metadata to compute the asset price.
- Impact: If this reader is used by `InitOracle`, an attacker can manipulate collateral or debt pricing, enabling undercollateralized borrowing, blocked liquidations, unfair liquidations, or oracle DoS.

## Any user can rewrite another user’s margin order

- Location: `contracts/hook/MarginTradingHook.sol` : `updateOrder`
- Mechanism: `updateOrder()` checks only that the caller has some valid `_posId`; it never checks `order.initPosId == initPosIds[msg.sender][_posId]`. It also fails to validate `_tokenOut` against the position’s base/quote assets and bounds `_collAmt` against the caller’s collateral, not the order owner’s collateral.
- Impact: Any margin user can modify any active order’s trigger price, limit price, tokenOut, and size, then fill the victim’s order at attacker-chosen terms to steal value from the victim’s collateral.

## Fill-order repay amount and debt shares are swapped

- Location: `contracts/hook/MarginTradingHook.sol` : `_calculateRepaySize`, `_calculateFillOrderInfo`, `fillOrder`
- Mechanism: `_calculateRepaySize()` declares returns as `(uint repayAmt, uint repayShares)`, but callers destructure it as `(repayShares, repayAmt)`. After interest accrues and debt shares are no longer 1:1 with debt amount, `fillOrder()` uses debt amount where shares are expected and shares where token amount is expected.
- Impact: Stop-loss and take-profit orders can become unfillable or settle with incorrect amounts. An attacker can wait for/accrue interest so protective orders revert, leaving positions exposed to liquidation.

## Margin orders can be reentered before status is updated

- Location: `contracts/hook/MarginTradingHook.sol` : `fillOrder`
- Mechanism: `fillOrder()` performs external token transfers and core calls while the order status is still `Active`; `__orders[_orderId].status = Filled` is written only at the end. Combined with the missing `_tokenOut` validation in `updateOrder()`, an attacker can set a malicious token as `tokenOut` and reenter `fillOrder()` during `safeTransferFrom`.
- Impact: The same order can be filled multiple times in one transaction, repeatedly decollateralizing the victim’s position until health or collateral checks stop the attack.

## Unattributed pool balances can be stolen

- Location: `contracts/lending_pool/LendingPool.sol` : `mint`, `burn`; `contracts/core/PosManager.sol` : `addCollateral`
- Mechanism: `LendingPool.mint()` mints shares from the pool’s raw balance delta, `burn()` redeems all pool shares held by the pool contract, and `PosManager.addCollateral()` credits collateral from the position manager’s raw balance delta. None of these flows bind the transferred assets to the depositor.
- Impact: If a user or integration transfers underlying to a pool, pool shares to the pool, or pool shares to `PosManager` outside an atomic trusted multicall, an attacker can front-run the follow-up call and mint, redeem, or collateralize the victim’s assets to themselves.

## Unattributed wrapped LP NFTs can be claimed by any position

- Location: `contracts/core/PosManager.sol` : `addCollateralWLp`
- Mechanism: `addCollateralWLp()` only checks that `PosManager` owns the wrapped LP NFT and that it is not already collateralized. It does not record or verify who transferred the NFT into `PosManager`.
- Impact: After a user transfers a wLP NFT to `PosManager` but before they collateralize it, any authorized position owner can collateralize that NFT to their own position and borrow against or withdraw the victim’s asset.

## Public callback can spend Core ETH and spoof Core-origin calls

- Location: `contracts/core/InitCore.sol` : `callback`
- Mechanism: `callback()` is public, accepts arbitrary `_to`, `_value`, and `_data`, and does not require `_value <= msg.value`. It forwards ETH already held by the core/proxy and makes the external call with `msg.sender == CORE`.
- Impact: Any ETH held by the core proxy can be drained through an attacker-controlled callback receiver. Integrations that trust `msg.sender == CORE` without also validating the `_sender` parameter can have privileged callback paths spoofed.

## Pyth prices are accepted without confidence bounds

- Location: `contracts/oracle/PythOracleReader.sol` : `getPrice_e36`
- Mechanism: The reader calls `getPriceUnsafe()` and discards Pyth’s `conf` value, enforcing only staleness. A price with extremely wide confidence is treated the same as a precise price.
- Impact: During high-uncertainty Pyth updates, the protocol can overvalue collateral, undervalue debt, or trigger unfair liquidations using a price Pyth itself marks as unreliable.

