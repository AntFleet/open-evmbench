# Audit: 2024-07-benddao

## Isolated auction collateral goes to the liquidation caller
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateLiquidate`
- Mechanism: After an isolate auction ends, the code never checks that `params.msgSender` is `loanData.lastBidder`. It consumes the winning bid to repay the loan, but transfers or reassigns the NFT to `params.msgSender`.
- Impact: Any address can finalize someone else’s winning auction and receive the NFT while the real winning bidder pays. The borrower can also self-liquidate and recover their NFT using the bidder’s escrow.

## Isolated liquidation overdraws bid escrow
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateLiquidate`
- Mechanism: When accrued debt exceeds the winning bid, `extraBorrowAmount` is collected separately from the liquidator, but the function still moves the full `totalBorrowAmount` out of `totalBidAmout` via `erc20TransferOutBidAmountToLiqudity`. The escrow only contains the bid amount, not `bid + extra`.
- Impact: Normal liquidations can revert from escrow underflow after interest accrues, leaving bad isolate debt unliquidatable. If other auctions’ escrow masks the underflow, their escrow is silently consumed and `availableLiquidity` is inflated.

## Isolate repay can mutate another user’s loan
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateRepay`
- Mechanism: The function loads the target loan by `nftAsset/tokenId`, but decreases isolate debt from caller-supplied `params.onBehalf`. It never verifies that `params.onBehalf` is the NFT owner or borrower for that loan.
- Impact: A user with isolate debt in the same group can repay against another user’s NFT loan, reduce their own accounting debt, and delete or reduce the victim’s loan record. This can unlock collateral incorrectly and corrupt per-user debt attribution.

## Isolate auction redeem is not borrower-restricted
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateRedeem`
- Mechanism: Redeem reduces debt for `params.msgSender` and updates the target NFT’s `loanData`, but it never checks that `params.msgSender` owns the auctioned NFT. The function can reset another borrower’s auction back to active status.
- Impact: A third party with compatible isolate debt can cancel or partially cancel another user’s auction, refund the highest bidder, and desynchronize loan debt from borrower debt accounting.

## Cross ERC721 liquidation can seize collateral without repaying actual debt
- Location: `src/libraries/logic/LiquidationLogic.sol` : `executeCrossLiquidateERC721`
- Mechanism: The ERC721 liquidation path does not require the borrower to owe the chosen `debtAsset`. If `_repayUserERC20Debt` cannot find debt in that asset, the unpaid amount is credited as new supplied collateral to the borrower, yet the selected NFT is still transferred to the liquidator.
- Impact: A liquidator can take an underwater borrower’s NFT by paying an unrelated ERC20, leaving the borrower’s real debt outstanding and stripping the protocol of the collateral that backed it.

## Yield debt shares are global across pool IDs
- Location: `src/yield/YieldStakingBase.sol` : `convertToDebtShares`, `convertToDebtAssets`, `_stake`, `_repay`
- Mechanism: `totalDebtShare` is global, but `getTotalDebt(poolId)` is pool-specific. Staking through a second pool with a different debt base changes the global share denominator used to value existing positions in other pools.
- Impact: An attacker can dilute existing debt shares, make old positions appear to owe less than they borrowed, repay the understated amount, unlock NFTs, and leave unassigned pool debt behind.

## Yield borrow caps use the borrow index as the supply index
- Location: `src/libraries/logic/YieldLogic.sol` : `executeYieldBorrowERC20`
- Mechanism: The cap denominator is computed with `VaultLogic.erc20GetTotalCrossSupply(assetData, groupData.borrowIndex)`. That helper expects the asset supply index, not the yield group borrow index. Borrow indexes usually grow faster than supply indexes.
- Impact: A whitelisted yield manager can borrow more than the configured asset-level and manager-level yield caps allow, increasing undercollateralized exposure beyond governance limits.

## Bot-admin yield unwinds use the bot’s yield account
- Location: `src/yield/YieldStakingBase.sol` : `_unstake`, `_repay`
- Mechanism: Both paths resolve `yieldAccounts[msg.sender]`. When `botAdmin` calls on behalf of an unhealthy user, `msg.sender` is the bot, while the actual position account is stored in `sd.yieldAccount`.
- Impact: Forced unstake/repay either reverts or operates on the wrong yield account, making unhealthy yield positions difficult or impossible to unwind and allowing bad debt to persist.

## Whitelisted yield managers can lock arbitrary isolate NFTs
- Location: `src/libraries/logic/YieldLogic.sol` : `executeYieldSetERC721TokenData`
- Mechanism: Any address with a nonzero manager yield cap for the debt asset can set `lockerAddr` on any isolate-supplied NFT whose locker is currently zero. There is no owner or operator approval check.
- Impact: A whitelisted but malicious yield manager can lock users’ NFTs, blocking withdrawal, supply-mode changes, and isolate borrowing until that manager unlocks them.

## Chainlink prices can be used indefinitely after feed staleness
- Location: `src/PriceOracle.sol` : `getAssetPriceFromChainlink`
- Mechanism: The oracle checks `answer > 0`, `updatedAt != 0`, and `answeredInRound >= roundId`, but never enforces a maximum age for `updatedAt`.
- Impact: If a feed stops updating during a market move, borrowing, health-factor checks, and liquidations continue using obsolete prices, enabling overborrowing or incorrect liquidations.

## Cross-borrow cap checks ignore accrued interest
- Location: `src/libraries/logic/BorrowLogic.sol` : `executeCrossBorrowERC20`
- Mechanism: `validateCrossBorrowERC20Basic` checks `borrowCap` before `InterestLogic.updateInterestIndexs` is called. The cap calculation therefore uses stale stored borrow indexes and excludes interest accrued since the last update.
- Impact: Borrowers can open new cross-borrows even when current debt including accrued interest should already exceed the configured borrow cap.

## ERC721 delegations persist across owner changes
- Location: `src/libraries/logic/PoolLogic.sol` : `executeDelegateERC721`
- Mechanism: Delegations are registered from the pool/vault address in Delegate Registry V2, but they are never revoked when the NFT is withdrawn, liquidated, or internally transferred to a new depositor.
- Impact: A previous owner’s delegate can retain rights over the same NFT when it is later held by the pool for another user, enabling theft or griefing of delegated claims, airdrops, or gated NFT actions.

