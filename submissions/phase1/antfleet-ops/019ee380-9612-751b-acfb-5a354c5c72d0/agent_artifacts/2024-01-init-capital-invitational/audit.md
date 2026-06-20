# Audit: 2024-01-init-capital-invitational

## Missing access control on LSD oracle configuration setters
- Location: `contracts/oracle/LsdApi3OracleReader.sol` : `setDataFeedIds`, `setQuoteTokens`, `setMaxStaleTimes`
- Mechanism: In every other oracle reader in the codebase the configuration setters are gated by the `onlyGovernor` modifier (see `Api3OracleReader.setDataFeedIds`, `Api3OracleReader.setMaxStaleTimes`, `PythOracleReader.setPriceIds`, `InitOracle.setPrimarySources`, etc.). In `LsdApi3OracleReader` only `setApi3OracleReader` carries `onlyGovernor`; the three feed‑configuration functions are declared plain `external` with no role check:
  ```solidity
  function setDataFeedIds(address[] calldata _tokens, bytes32[] calldata _dataFeedIds) external { ... }
  function setQuoteTokens(address[] calldata _tokens, address[] calldata _quoteTokens) external { ... }
  function setMaxStaleTimes(address[] calldata _tokens, uint96[] calldata _maxStaleTimes) external { ... }
  ```
  These directly write `dataFeedInfos[_token].dataFeedId`, `.quoteToken`, and `.maxStaleTime`, which are exactly the values consumed by `getPrice_e36` to compute the reported price (`rate_e18.toUint256().mulDiv(quotePrice_e36, ONE_E18)`).
- Impact: Any unauthorized address can repoint an LSD token’s `dataFeedId` to an Api3 feed of arbitrary value, swap its `quoteToken` to a high‑priced asset, and/or relax `maxStaleTime` to disable staleness protection. Because this oracle feeds `InitOracle` → `InitCore.getCollateralCreditCurrent_e36`/`getBorrowCreditCurrent_e36`, an attacker can arbitrarily inflate the price of an LSD collateral token (or deflate a borrowed token), make an undercollateralized position appear healthy, and borrow out the lending pools’ assets — or, conversely, force healthy positions underwater to liquidate them. This is a complete compromise of the protocol’s solvency via oracle manipulation.

## Repay amount / repay shares are swapped in margin order filling
- Location: `contracts/hook/MarginTradingHook.sol` : `_calculateRepaySize` (and its caller `_calculateFillOrderInfo` / `fillOrder`)
- Mechanism: `_calculateRepaySize` is declared `returns (uint repayAmt, uint repayShares)` but its body computes shares into the variable named `repayShares` and the token amount into `repayAmt`, so it returns positionally `(amount, shares)`. The caller destructures the opposite way:
  ```solidity
  (repayShares, repayAmt) = _calculateRepaySize(_order, _marginPos);
  ```
  so within `_calculateFillOrderInfo`/`fillOrder` the variable `repayShares` actually holds the token *amount* and `repayAmt` holds the *share* count. `fillOrder` then does `IERC20(borrToken).safeTransferFrom(msg.sender, address(this), repayAmt)` (pulling a *share count* worth of tokens from the filler) and `IInitCore(CORE).repay(marginPos.borrPool, repayShares, order.initPosId)` (passing a token *amount* where debt *shares* are expected). The `amtOut` formulas in `_calculateFillOrderInfo` likewise multiply `repayAmt` (shares) as though it were a repay amount.
- Impact: Since debt amount per share is ≥ 1 (and grows with accrued interest), `repay` is invoked with an inflated share figure that `InitCore._repay` clamps to the full position debt, while the filler is only charged the much smaller raw‑share quantity of the borrow token. An order filler can settle a position’s entire debt while transferring in far fewer tokens than the debt is worth (the shortfall being drawn from the hook/other users), and the payout calculation is corrupted — letting the order owner/filler extract value at the protocol’s expense, or at minimum bricking order execution.

