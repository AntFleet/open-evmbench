# Audit: 2024-07-benddao
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

Below is the merged report. I cataloged **13 distinct findings** across the 6 input reports (2 models × 3 shots, M = 6) by code path + root cause, and all 13 appear in the output (7 consensus + 6 minority). Note: the claude-opus-4-8 shot-3 report arrived truncated at the top; I attributed to it the oracle and yield-cap findings present in its visible body plus the NFT-to-`msg.sender` theft it names in its closing note ("the clearly planted, highest-impact bug is the first one").

---

# Merged Security Audit Report

## Consensus findings

## Yield-borrow cap computed against supply scaled by the borrow index
*(consensus, 6 of 6 reports)*
- Location: `src/libraries/logic/YieldLogic.sol` : `executeYieldBorrowERC20`
- Mechanism: `vars.totalSupply = VaultLogic.erc20GetTotalCrossSupply(assetData, groupData.borrowIndex)` scales total cross supply by the yield group's **borrow** index instead of the asset **supply** index (`assetData.supplyIndex` / `getNormalizedSupplyIncome`). Both indices seed at `RAY`, but the borrow index grows faster (borrow rate ≥ supply rate, and supply also pays a protocol fee), so `totalSupply` is overstated. That inflated value is the ceiling in both the asset-level check (`(totalBorrow + amount) <= totalSupply.percentMul(assetData.yieldCap)`) and the per-manager check (`... percentMul(ymData.yieldCap)`).
- Impact: A whitelisted/approved yield manager can draw **uncollateralized** liquidity beyond the configured asset- and manager-level caps, by roughly the `borrowIndex/supplyIndex` ratio, which widens as the asset ages. This erodes the liquidity buffer backing supplier withdrawals and breaks an explicit risk invariant.

## Chainlink (and NFT) oracle reads have no staleness / heartbeat bound
*(consensus, 5 of 6 reports)*
- Location: `src/PriceOracle.sol` : `getAssetPriceFromChainlink` (and transitively `getAssetPrice`, `getAssetPriceFromBendNFTOracle`)
- Mechanism: The read enforces only `answer > 0`, `updatedAt != 0`, and the deprecated `answeredInRound >= roundId`. It never checks `block.timestamp - updatedAt <= heartbeat`, so a frozen feed that keeps returning its last completed round is accepted as current. The `getAssetPriceFromBendNFTOracle` path exposes only a price with no freshness guard at all. This price feeds `calculateUserAccountData`/`GenericLogic`, borrow-LTV validation, health-factor and all liquidation math, plus the NFT base-currency conversion.
- Impact: If a feed stalls (or lags during a real market move), borrowers can over-borrow against stale-high collateral, or liquidators can seize collateral / trigger liquidations at stale-favorable prices — the classic flash-crash/stale-oracle exposure causing bad debt or unfair liquidations. (`answeredInRound >= roundId` is deprecated and does not substitute for a heartbeat check.)

## Isolate redeem decrements the caller's debt, not the loan owner's, with no owner check
*(consensus, 3 of 6 reports)*
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateRedeem`; validators `ValidateLogic.validateIsolateRedeemBasic` / `validateIsolateRedeemLoan`
- Mechanism: A loan's debt is tracked twice — `loanData.scaledAmount` (loan level) and `groupData.userScaledIsolateBorrow[borrower]` (per-account). At borrow time the scaled debt is credited to `onBehalf`, but redeem reduces `loanData.scaledAmount` while decrementing `userScaledIsolateBorrow[params.msgSender]`, and no validator checks that `msgSender` owns the auctioned loan. A caller holding their own isolate debt in the same group can redeem someone else's loan (resetting it to active, refunding the bidder) while the reduction lands on the wrong aggregate.
- Impact: Per-account isolate accounting desyncs from `loanData.scaledAmount` and `totalScaledIsolateBorrow`: the real borrower is overstated, the caller understated, leaving phantom/dust debt and a corrupted query layer. A later legitimate repay/liquidate can underflow on `userScaledIsolateBorrow` and revert, locking an NFT; on full liquidation the burn uses the reduced loan amount, leaving group/user totals inconsistent. Redeem should target the loan's borrower and restrict the caller.

## Isolate auction settlement transfers the NFT to the caller instead of the winning bidder
*(consensus, 2 of 6 reports)*
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateLiquidate`; exposed via `src/modules/IsolateLiquidation.sol` : `isolateLiquidate`
- Mechanism: The auction records `loanData.lastBidder`, but final settlement (the path commented `// transfer erc721 to bidder`) transfers the NFT / internal isolate-supply position to `params.msgSender` rather than to `loanData.lastBidder`.
- Impact: After an auction ends, any attacker can call `isolateLiquidate` first and receive the auctioned NFT while the winning bidder's escrowed bid repays the debt — if the bid covers the debt, the attacker pays nothing. This is theft of every auctioned NFT (flagged as the highest-impact, clearly planted bug).

## Isolate liquidation over-credits liquidity from the shared bid escrow
*(consensus, 2 of 6 reports)*
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateLiquidate` (the settlement block: `erc20TransferOutBidAmountToLiqudity(debtAssetData, vars.totalBorrowAmount)` followed by `erc20TransferInLiquidity(..., vars.totalExtraAmount)`); `src/libraries/logic/VaultLogic.sol` : `erc20TransferOutBidAmountToLiqudity`
- Mechanism: The escrow actually held in `assetData.totalBidAmout` for these loans is `sum(min(bid,borrow)) = totalBorrowAmount − totalExtraAmount`. But the code passes the full `totalBorrowAmount` to `erc20TransferOutBidAmountToLiqudity` (which does `totalBidAmout -= amount; availableLiquidity += amount`) and *then* adds the liquidator's `totalExtraAmount` again via `erc20TransferInLiquidity`. Net: `availableLiquidity` is inflated by `totalExtraAmount` and `totalBidAmout` is over-debited by `totalExtraAmount`. Because debt accrues interest over the (up to 7-day) auction window, `borrow > bid` is the normal case, so `totalExtraAmount > 0` on essentially every isolate liquidation. `erc20TransferOutBidAmountToLiqudity` has no `>=` guard. The correct amount is `totalBorrowAmount − totalExtraAmount`.
- Impact: (1) DoS/funds-lock — if `totalBidAmout` lacks other escrow (e.g. the only active auction), the subtraction underflows and the liquidation reverts, so underwater NFT loans become permanently un-liquidatable (bad-debt DoS). (2) Escrow theft — when other auctions pad `totalBidAmout`, each liquidation siphons `totalExtraAmount` of *other bidders'* escrow into freely-withdrawable `availableLiquidity`; the entitled bidder/borrower can no longer be refunded (`erc20TransferOutBidAmount` underflows), and an attacker can repeatedly trigger this and withdraw the phantom liquidity.

## Liquidated isolate NFTs keep stale lock state
*(consensus, 2 of 6 reports)*
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateLiquidate`; `src/libraries/logic/VaultLogic.sol` : `erc721DecreaseIsolateSupplyOnLiquidate` (and `erc721TransferIsolateSupplyOnLiquidate`)
- Mechanism: Isolate borrow sets `tokenData.lockerAddr = address(this)`. On liquidation the loan is deleted, but `lockerAddr` is never cleared; the transfer/decrease helpers update owner and supply mode while leaving the stale locker in storage. A later deposit checks only `owner == address(0)` and overwrites owner/mode without resetting `lockerAddr`.
- Impact: A liquidator using `supplyAsCollateral` receives an internally locked position, and a previously liquidated NFT that is later re-deposited can become non-withdrawable because withdraw and supply-mode-change paths require `lockerAddr == address(0)`. Cross-mode redeposits are especially stuck, since the user cannot open/repay an isolate loan to clear the lock.

## Isolate repay burns the caller-supplied account's debt, not the loan owner's
*(consensus, 2 of 6 reports)*
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateRepay`; validator `ValidateLogic.validateIsolateRepayLoan`
- Mechanism: Repay updates the selected NFT loan's `loanData.scaledAmount` (and may delete the loan / unlock the NFT) but decrements isolate debt from caller-supplied `params.onBehalf` (`erc20DecreaseIsolateScaledBorrow(debtGroupData, params.onBehalf, vars.scaledRepayAmount)`) without checking that `onBehalf` is the loan owner. A borrower with debt in the same reserve group can repay their own accounting debt while clearing a *different* account's NFT loan state.
- Impact: Isolate loan accounting desyncs — one NFT is freed from its loan while bad/stuck debt is left attached to another account; `loanData.scaledAmount`, `userScaledIsolateBorrow`, and `totalScaledIsolateBorrow` diverge, and a later legitimate repay/liquidate can revert on underflow. Preconditions: the attacker controls/colludes with an account holding isolate debt in the same debt asset/group.

---

## Minority findings

## Flash-loan repayment does not verify the returned token balance
*(minority, 1 of 6 reports)* *(conflicting reviews: 2 of 6 reports defended this code path)*
- Location: `src/libraries/logic/FlashLoanLogic.sol` : `executeFlashLoanERC20`; `src/libraries/logic/VaultLogic.sol` : `erc20TransferInOnFlashLoan`
- Mechanism: Normal ERC20 liquidity transfers enforce exact balance deltas, but flash-loan repayment only calls `safeTransferFrom` for the principal and never checks that the pool balance actually increased by `amount`. Fee-on-transfer, rebasing, or other non-standard tokens can return less than `amount` while the flash loan still succeeds.
- Impact: If such a token is listed and flash loans are enabled, an attacker can repeatedly flash-loan it and return less than borrowed, creating an unaccounted token-balance shortfall while `availableLiquidity` stays unchanged.
- Reviewer disagreement: claude-opus-4-8 shots 1–2 asserted that "every transfer asserts exact balance deltas" / "physical-token transfer/balance checks prevent withdrawing more than is actually present," and so judged the flash-loan path sound.

## Fee-free flash loan with stale accounted liquidity and no reentrancy guard
*(minority, 1 of 6 reports)* *(conflicting reviews: 3 of 6 reports defended this code path)*
- Location: `src/modules/FlashLoan.sol` : `flashLoanERC20`; `src/libraries/logic/FlashLoanLogic.sol` : `executeFlashLoanERC20`; `src/libraries/logic/VaultLogic.sol` : `erc20TransferOutOnFlashLoan`, `erc20TransferInOnFlashLoan`
- Mechanism: ERC20 flash loans transfer tokens out, call the receiver, then require only the exact principal back — no premium is charged and `assetData.availableLiquidity` is never reduced during the loan. Because `flashLoanERC20` is intentionally not `nonReentrant`, the receiver can reenter other pool functions while storage still reports pre-loan liquidity.
- Impact: Anyone gets free flash loans; more importantly, during the callback, reentrant code observes overstated `availableLiquidity`, opening a cross-function reentrancy window that can affect borrow/withdraw/liquidation paths relying on accounted liquidity. The final principal check prevents direct theft of the flashed amount.
- Reviewer disagreement: all three claude-opus-4-8 shots noted `flashLoanERC20` deliberately omits `nonReentrant` but concluded it "does not mutate internal accounting"/"re-entry yields nothing exploitable" and explicitly declined to report it.

## Native ERC20 withdraw uses the wrong amount and receiver
*(minority, 1 of 6 reports)*
- Location: `src/modules/BVault.sol` : `withdrawERC20`; `src/libraries/logic/SupplyLogic.sol` : `executeWithdrawERC20`; `src/libraries/logic/VaultLogic.sol` : `unwrapNativeTokenInWallet`
- Mechanism: Native withdrawals convert the sentinel asset to WETH, then `executeWithdrawERC20` sends WETH liquidity to the caller-supplied `receiver`. Afterward `withdrawERC20` calls `unwrapNativeTokenInWallet(asset, msgSender, amount)`, which pulls WETH from `msgSender` via `transferFrom`, unwraps, and sends ETH to `msgSender` — ignoring the `receiver` that already got the WETH and reusing the original `amount` even though `executeWithdrawERC20` may have capped `params.amount` down to the user's balance.
- Impact: If `receiver != msgSender`, the pool pays WETH to `receiver` but then pulls WETH from `msgSender` (draining unrelated WETH if approved, reverting otherwise). For "withdraw max" calls where the request exceeds balance, the internal amount is capped but the unwrap still uses the larger original amount, causing a denial of service.

## Zero-scaled isolate borrows can create unaccounted debt
*(minority, 1 of 6 reports)*
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateBorrow`; `src/libraries/logic/VaultLogic.sol` : `erc20IncreaseIsolateScaledBorrow`
- Mechanism: `executeIsolateBorrow` computes `amountScaled = amount.rayDiv(borrowIndex)` and passes it to `erc20IncreaseIsolateScaledBorrow`, which does not reject `amountScaled == 0`. For a sufficiently large borrow index, small positive borrow amounts round down to zero scaled debt while the full token `amount` is still transferred out.
- Impact: A borrower with isolate NFT collateral can repeatedly borrow amounts that round to zero scaled debt and then clear the zero-scaled loan with no repayment, draining available liquidity in small increments. Preconditions: a sufficiently high borrow index and available pool liquidity.

## Deploy script validates the wrong variable before setting the treasury
*(minority, 1 of 6 reports)*
- Location: `script/DeployPoolFull.s.sol` : `_deployAddressProvider`
- Mechanism: Before setting the treasury, the script runs `require(addressInCfg == address(0), 'Invalid Treasury in config')`, re-checking the already-asserted AddressProvider address instead of the `treasury` value, so a zero/garbage treasury passes the guard at deploy time.
- Impact: A misconfigured (zero) treasury can be accepted at deployment; fee collection later requires a non-zero treasury, so impact is limited but the guard is non-functional.

## Enabling asset yield leaves the rate model unset, bricking later interest updates
*(minority, 1 of 6 reports)*
- Location: `src/libraries/logic/ConfigureLogic.sol` : `executeSetAssetYieldEnable`
- Mechanism: The function adds the yield group (`groupList.add(yieldGroup)`, `initGroupData`) but leaves `groupData.rateModel == address(0)`. Until `setAssetYieldRate` is called, every `InterestLogic.updateInterestRates` for that asset invokes `IInterestRateModel(address(0)).calculateGroupBorrowRate(...)` and reverts.
- Impact: Deposits/withdraws/borrows/repays for the asset are bricked until the yield rate model is set. Admin-only and recoverable, but it is a setter that admits a state which bricks downstream logic.

