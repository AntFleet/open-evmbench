# Audit: 2024-01-init-capital-invitational

An audit of the provided codebase has been conducted, and several genuine security vulnerabilities have been identified. They are reported below in detail, categorizing each based on location, mechanism, and impact.

---

## Complete DoS on Stop Loss and Take Profit Fills of Unhealthy Positions
- **Location**: `MarginTradingHook.sol` : `fillOrder()` (and in `InitCore.sol` : `decollateralize()`)
- **Mechanism**: The loop inside `fillOrder()` executes a call to `IInitCore(CORE).decollateralize(...)` to distribute the order's collateral to the arbitrageur after debt is repaid. However, `InitCore.decollateralize()` implements the `ensurePositionHealth` modifier:
  ```solidity
  modifier ensurePositionHealth(uint _posId) {
      if (isMulticallTx) uncheckedPosIds.add(_posId);
      _;
      if (!isMulticallTx) _require(_isPosHealthy(_posId), Errors.POSITION_NOT_HEALTHY);
  }
  ```
  Since `fillOrder()` is executed outside of a multicall, the health check `_isPosHealthy` is performed immediately at the end of the `decollateralize` call. If the position is already unhealthy (health factor $< 1.0$), or if the market has moved such that the proportional close still leaves the rest of the position with a health factor $< 1.0$, `_isPosHealthy` will return `false`, causing the transaction to revert.
- **Impact**: Order fillers (arbitrageurs) will never be able to execute any Stop Loss or Take Profit orders on positions that have dropped below a health factor of $1.0$. This completely disables the stop-loss mechanism when users need it most—during rapid down-turns where their position becomes slightly unhealthy—leaving their positions exposed to direct liquidation instead of being safely closed by the hook at the defined trigger/limit prices.

---

## Inability to Fully Liquidate Unhealthy Positions (Permanent Revert for Complete Debt Payoffs)
- **Location**: `InitCore.sol` : `_ensurePosHealthAfterLiq()`
- **Mechanism**: During a liquidation, `InitCore` checks that the position's health factor after being liquidated does not exceed the configured threshold via:
  ```solidity
  function _ensurePosHealthAfterLiq(IConfig _config, uint _posId, uint16 _mode) internal {
      uint healthAfterLiquidation_e18 = _config.getMaxHealthAfterLiq_e18(_mode);
      if (healthAfterLiquidation_e18 != type(uint64).max) {
          _require(
              getPosHealthCurrent_e18(_posId) <= healthAfterLiquidation_e18, Errors.INVALID_HEALTH_AFTER_LIQUIDATION
          );
      }
  }
  ```
  However, if a liquidator completely repays the outstanding debt of a position, its remaining borrow credit becomes `0`. Under `getPosHealthCurrent_e18()`, if borrow credit is `0`, the function returns `type(uint).max`. Since `type(uint).max` is always strictly greater than `healthAfterLiquidation_e18` (which is typically a low value representing around $1.05 \times 10^{18}$ to $1.1 \times 10^{18}$), the call will unconditionally revert with `INVALID_HEALTH_AFTER_LIQUIDATION`.
- **Impact**: Liquidators can never fully liquidate an unhealthy position (or execute a partial liquidation that repays the final remainder of the debt) because the health check after a full debt payoff evaluates to infinity and triggers a revert. This leaves lingering bad/unhealthy dust positions stuck in the protocol.

---

## Universal DoS via SafeERC20.safeApprove Non-Zero to Non-Zero Restriction
- **Location**: `MoeSwapHelper.sol` : `_ensureApprove()`, `MoneyMarketHook.sol` : `_ensureApprove()`, `BaseMappingIdHook.sol` : `_ensureApprove()`
- **Mechanism**: Spanning multiple wrappers and hooks is the helper function `_ensureApprove` implemented as follows:
  ```solidity
  function _ensureApprove(address _token, uint _amt) internal {
      if (IERC20(_token).allowance(address(this), ROUTER) < _amt) {
          IERC20(_token).safeApprove(ROUTER, type(uint).max);
      }
  }
  ```
  The OpenZeppelin `SafeERC20.safeApprove` implementation has a strict validation rule to prevent approval race conditions: it reverts if both the current allowance and the newly requested allowance are non-zero. If any previous operation leaves a non-zero residual allowance on the contract (e.g. from partial slippage, exact-out swaps, or a token like USDT with non-standard behavior) and a subsequent operation requires an approval amount $\text{allowance} < \text{\_amt}$, the call to `safeApprove` will unconditionally revert.
- **Impact**: These hooks and swap helpers will be permanently bricked (DoS) for any token that enters a state with a non-zero, non-infinite allowance, trapping user funds and blocking critical features such as Margin Trading and Money Market operations.

---

## Decimal Mismatch in LsdApi3OracleReader Causes Radical Price Underestimation
- **Location**: `LsdApi3OracleReader.sol` : `getPrice_e36()`
- **Mechanism**: The LSD API3 price reader calculates the price of a yield-bearing derivative using the exchange rate dAPI and the quote token price:
  ```solidity
  price_e36 = rate_e18.toUint256().mulDiv(quotePrice_e36, ONE_E18);
  ```
  This formula assumes that the derivative token (`_token`) and the `
