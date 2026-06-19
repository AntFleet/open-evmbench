# Audit: 2024-06-size

## Critical: ETH Balance Sweep in Deposit
- Location: `src/libraries/actions/Deposit.sol` : `executeDeposit`
- Mechanism: When a user deposits ETH (`msg.value > 0`), the contract calculates the deposit amount using `amount = address(this).balance` instead of `msg.value`. This was likely done to handle `msg.value` persistence across a `multicall` batch, but it incorrectly sweeps the entire ETH balance of the contract. 
- Impact: If the contract holds any residual ETH (e.g., from forced transfers, self-destruct, or rounding dust), the next user who calls `deposit` with any `msg.value > 0` (even 1 wei) will wrap and receive credit for the entire ETH balance of the contract, stealing funds that do not belong to them. Additionally, in a legitimate `multicall` with multiple ETH deposits, the first call will consume the entire `msg.value`, causing subsequent deposit calls in the same batch to fail or deposit 0.

## Critical: Liquidation Reward Unit Mismatch
- Location: `src/libraries/actions/Liquidate.sol` : `executeLiquidate`
- Mechanism: The liquidator reward is calculated as `Math.mulDivUp(debtPosition.futureValue, state.feeConfig.liquidationRewardPercent, PERCENT)`. However, `debtPosition.futureValue` is denominated in **borrow tokens** (e.g., USDC), while the reward is paid out in **collateral tokens** (e.g., ETH) and added to `liquidatorProfitCollateralToken`. The code fails to convert `futureValue` to collateral tokens (using `debtInCollateralToken`) before applying the percentage.
- Impact: Because borrow and collateral tokens have different decimals and unit prices, the reward amount will be drastically miscalculated. For example, if the debt is 1,000 USDC (`1e9` in 6 decimals) and collateral is ETH (18 decimals), a 5% reward yields `5e7` wei of ETH (0.00000005 ETH) instead of the intended 5% of the debt's collateral value. This effectively eliminates the liquidation incentive, leading to unliquidatable underwater positions and potential protocol insolvency.

## Medium: Fee Evasion in Compensate via Balance Capping
- Location: `src/libraries/actions/Compensate.sol` : `executeCompensate`
- Mechanism: When a credit position is fractionally compensated, a fragmentation fee is charged in collateral tokens. The fee amount is explicitly capped by the user's current collateral balance: `Math.min(feeInCollateral, state.data.collateralToken.balanceOf(msg.sender))`. 
- Impact: A user can intentionally withdraw their collateral down to the minimum required to avoid liquidation (`crLiquidation`) right before calling `compensate`. If their remaining collateral balance is lower than the required fragmentation fee, they will pay a reduced fee or zero fee, allowing them to evade protocol fees. The transaction should revert if the user lacks the balance to pay the full fee, rather than silently discounting it.

## Medium: Missing `answeredInRound` Check in Chainlink Oracle
- Location: `src/oracle/PriceFeed.sol` : `_getPrice`
- Mechanism: The oracle fetches price data using `aggregator.latestRoundData()` and checks if the price is positive and if `updatedAt` is within the stale interval. However, it omits the standard Chainlink safety check: `require(answeredInRound >= roundId, "Stale price")`.
- Impact: If a round is currently ongoing and has not yet been answered by the oracle network, `latestRoundData()` may return data from a previous round. While the `updatedAt` timestamp check provides some protection, it is not foolproof in all Chainlink proxy implementations and can theoretically allow the protocol to accept and price loans using stale data from an incomplete round.

## Low: Admin Cannot Increase Liquidation Collateral Ratio
- Location: `src/libraries/actions/UpdateConfig.sol` : `executeUpdateConfig`
- Mechanism: When updating the `crLiquidation` parameter, the code enforces `if (params.value >= state.riskConfig.crLiquidation) revert`. This logic only allows the admin to decrease the liquidation threshold, not increase it.
- Impact: While this protects existing borrowers from having their loans forcefully liquidated by a threshold hike, it prevents the protocol governance from raising the liquidation ratio to safer levels in response to increased market volatility or risk model updates. If a higher `crLiquidation` is required for protocol safety, the admin is forced to redeploy or use a workaround.
