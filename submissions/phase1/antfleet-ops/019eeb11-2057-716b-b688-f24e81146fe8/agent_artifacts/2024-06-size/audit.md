# Audit: 2024-06-size
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Borrow aToken cap bypassable via multicall (wrong balance snapshotted)
*(consensus, 6 of 6 reports)*
- Location: `src/libraries/Multicall.sol` : `multicall` (the `borrowATokenSupplyBefore`/`borrowATokenSupplyAfter` snapshots), interacting with `src/libraries/actions/Deposit.sol` : `executeDeposit` and `src/libraries/CapsLibrary.sol` : `validateBorrowATokenCap` / `validateBorrowATokenIncreaseLteDebtTokenDecrease`.
- Mechanism: A standalone borrow-token deposit enforces the cap via `validateBorrowATokenCap()`, which compares `borrowAToken.totalSupply()` to `riskConfig.borrowATokenCap`. Inside a multicall this per-call check is deliberately skipped (`if (!state.data.isMulticall) state.validateBorrowATokenCap();`), delegating enforcement to the post-multicall guard `validateBorrowATokenIncreaseLteDebtTokenDecrease`. That guard snapshots `state.data.borrowAToken.balanceOf(address(this))` (the protocol's own holdings of unclaimed repaid cash) rather than `totalSupply()`. A deposit mints scaled tokens to the depositor (`mintScaled(to, …)`), raising `totalSupply()` but leaving `balanceOf(address(this))` unchanged, so the measured increase is always `0` and the guard never fires.
- Impact: Any user can wrap `deposit(underlyingBorrowToken, hugeAmount, self)` in a single-element `multicall` to mint borrow aTokens arbitrarily past `borrowATokenCap` (permanently — it is not re-checked at the end of the multicall), fully defeating the protocol's Aave-exposure/inflow risk limit, including a cap of zero set to halt new deposits. Risk-control bypass rather than direct theft.

## Idle/stranded ETH credited to the next WETH depositor
*(consensus, 4 of 6 reports)*
- Location: `src/libraries/actions/Deposit.sol` : `executeDeposit` (the `amount = address(this).balance;` branch when `msg.value > 0`); `src/Size.sol` payable user actions.
- Mechanism: The ETH path validates `msg.value` against `params.amount`, then replaces `amount` with `address(this).balance` before wrapping WETH and minting collateral to `params.to`. Because many entrypoints are `payable` and don't reject `msg.value` (and ETH can be force-sent), the contract can hold unaccounted idle ETH that the next ETH depositor wraps and is credited for in full, despite only supplying their own `msg.value`.
- Impact: If ETH is force-sent or accidentally left in the contract (e.g. via `repay{value:X}`), an attacker can make a valid WETH deposit with a tiny matching `msg.value` and receive collateral tokens for the entire contract ETH balance, then withdraw it. Low severity / precondition-dependent value-leak; partly an artifact of the intentional `address(this).balance` multicall design.

## Liquidator reward computed in debt-token units instead of collateral-token units
*(consensus, 2 of 6 reports)*
- Location: `src/libraries/actions/Liquidate.sol` : `executeLiquidate` — the `liquidatorReward = Math.min(...)` block, `Math.mulDivUp(debtPosition.futureValue, liquidationRewardPercent, PERCENT)`.
- Mechanism: `liquidatorReward` is a collateral-token quantity (added to `debtInCollateralToken`, bounded by collateral amounts), but the second `min` argument uses `debtPosition.futureValue`, denominated in the borrow token (USDC, 6 decimals) and *not* run through the oracle conversion `debtTokenAmountToCollateralTokenAmount(...)` that every other collateral term in the function uses. This treats 6-decimal USDC units as 18-decimal WETH units, making the reward ~1e12 (≈9–12 orders of magnitude) smaller than intended; the `min` then almost always selects this dust value. Correct expression is `mulDivUp(debtInCollateralToken, liquidationRewardPercent, PERCENT)`.
- Impact: Liquidators receive only the collateral-equivalent of repaid debt plus an effectively-zero premium (break-even at oracle price, no margin for gas/slippage). Rational keepers stop liquidating undercollateralized/overdue positions, so bad debt accrues and the protocol risks insolvency exactly when liquidations matter most; the suppressed reward also leaves extra `collateralRemainder` with the borrower. Affects all profitable-liquidation paths, including `liquidateWithReplacement`.
- Reviewer disagreement: Two reports broadly stated the liquidation logic / rounding "checks out" and "favors the protocol," without addressing this specific unit mismatch.

## Minority findings

## CEI violation in variable-pool borrow-token withdrawal (state burned after external transfer)
*(minority, 1 of 6 reports)* *(conflicting reviews: 2 of 6 reports defended this code path)*
- Location: `src/libraries/DepositTokenLibrary.sol` : `withdrawUnderlyingTokenFromVariablePool`.
- Mechanism: The function calls `state.data.variablePool.withdraw(underlyingBorrowToken, amount, to)` — sending the underlying token out — *before* computing `scaledAmount` and calling `borrowAToken.burnScaled(from, scaledAmount)`. At the moment funds leave, the depositor's accounted `borrowAToken` balance is still intact, so a re-entrant `withdraw` would see the full, not-yet-debited balance (`Math.min(params.amount, borrowAToken.balanceOf(msg.sender))`) and could withdraw again. The sibling collateral path burns before transferring, making this look like an oversight; the protocol has no `ReentrancyGuard` and `isMulticall` is not a reentrancy lock.
- Impact: Not exploitable with the current USDC/Aave configuration (no transfer callback). Latent cross-function reentrancy: if ever deployed with a borrow token that yields control on transfer (ERC-777/hooked/fee-on-transfer-with-callback), a depositor could drain the variable-pool position by re-entering before the scaled burn. `underlyingBorrowToken` is set from deployment params.
- Reviewer disagreement: Other reports asserted no CEI/reentrancy exposure because the only external calls are to trusted Aave and to USDC/WETH ERC-20s, which invoke no attacker-controlled callbacks before state is finalized.

## Sequencer-uptime feed missing `startedAt == 0` (invalid round) check
*(minority, 1 of 6 reports)* *(conflicting reviews: 2 of 6 reports defended this code path)*
- Location: `src/oracle/PriceFeed.sol` : `getPrice` (the `sequencerUptimeFeed` block, `if (block.timestamp - startedAt <= GRACE_PERIOD_TIME)`).
- Mechanism: When a sequencer uptime feed is configured, the code reads `(, answer, startedAt, , )` and treats the sequencer as healthy unless `answer == 1` or the grace period hasn't elapsed, but never validates `startedAt != 0`. Per Chainlink, `startedAt == 0` indicates an invalid/uninitialized round; then `block.timestamp - startedAt` is enormous, the grace-period guard passes, and the price is accepted while the uptime status is actually unknown.
- Impact: On an L2 deployment that wires up a `sequencerUptimeFeed`, a malformed/uninitialized round would let stale/unreliable prices flow into CR and liquidation math during a window when the sequencer's true state is unknown, enabling mispriced liquidations/borrows. Latent — every configuration shown sets `sequencerUptimeFeed = address(0)`, skipping the block.
- Reviewer disagreement: Other reports stated the oracle staleness / sequencer checks "appear sound."

## Scaled borrow-token transfers round down payment amounts
*(minority, 1 of 6 reports)* *(conflicting reviews: 3 of 6 reports defended this code path)*
- Location: `src/token/NonTransferrableScaledToken.sol` : `transferFrom`.
- Mechanism: The function converts an unscaled transfer `value` into scaled shares with `mulDivDown(value, RAY, liquidityIndex())`, then burns/mints only that floored scaled amount while emitting the original unscaled `value`. When the liquidity index exceeds `RAY`, the balance actually moved is smaller than the amount that repayment, liquidation, fee, and claim logic treat as transferred.
- Impact: Borrowers or liquidators can underpay debt, fees, or liquidation payments by up to the rounding dust per transfer while protocol accounting cancels the full unscaled amount. Small per operation, but amplifiable by splitting activity across many minimum-sized positions.
- Reviewer disagreement: Other reports stated the `NonTransferrableScaledToken` scaled-token accounting "checks out unit- and rounding-wise," with rounding "consistently favoring the protocol" and scaled/unscaled units used consistently.

---

*Recall check: 6 distinct findings identified across the 6 input reports (1 borrow-cap bypass, 1 idle-ETH credit, 1 liquidator-reward unit error, 1 CEI/reentrancy ordering, 1 sequencer `startedAt`, 1 scaled-transfer rounding); 6 findings emitted (3 consensus + 3 minority). No findings dropped.*

