# Audit: 2024-07-benddao

# BendDAO Security Audit Report

## Wrong index used for yield supply cap
- Location: `src/libraries/logic/YieldLogic.sol` : `executeYieldBorrowERC20`
- Mechanism: When enforcing asset- and staker-level yield caps, total cross-mode supply is computed with `VaultLogic.erc20GetTotalCrossSupply(assetData, groupData.borrowIndex)` instead of the supply index (`assetData.supplyIndex` / `InterestLogic.getNormalizedSupplyIncome`). Supply and borrow indices accrue on different schedules, so the denominator used for `yieldCap` checks is systematically wrong.
- Impact: Whitelisted yield stakers can borrow more uncollateralized liquidity than configured caps allow (typically once `borrowIndex` exceeds `supplyIndex`), draining lender funds beyond protocol risk limits.

## Flash loans bypass internal liquidity accounting
- Location: `src/libraries/logic/FlashLoanLogic.sol` : `executeFlashLoanERC20` / `executeFlashLoanERC721`; `src/modules/FlashLoan.sol` : `flashLoanERC20`
- Mechanism: Flash loans move underlying assets via `erc20TransferOutOnFlashLoan` / `erc721TransferOutOnFlashLoan`, which transfer directly from the vault balance without decrementing `availableLiquidity` (ERC20) or NFT `availableLiquidity`. They also do not respect `totalBidAmout` escrow segregation used by isolate auctions. `flashLoanERC20` deliberately omits the `nonReentrant` guard, allowing nested protocol calls during the callback while accounting still shows full lendable liquidity.
- Impact: An attacker can temporarily withdraw ERC20 held as auction bid escrow (and other non-lendable balances), causing bid refunds or isolate auction settlement to fail (DoS), or combine flash-loan reentrancy with other module calls while liquidity counters are stale. ERC721 flash loans similarly remove collateral from the vault without updating supply/liquidity counters, breaking invariants during the callback.

## ERC721 cross-liquidation over-allocates debt to a single asset
- Location: `src/libraries/logic/LiquidationLogic.sol` : `_calculateDebtAmountFromERC721Collateral` / `executeCrossLiquidateERC721`
- Mechanism: ERC721 liquidation debt is derived by allocating the borrower’s **total portfolio debt** proportionally to the liquidated NFT collateral (`inputCollateralInBaseCurrency * totalDebtInBaseCurrency / totalCollateralInBaseCurrency`), then converting that to the chosen `debtAsset`. Unlike ERC20 liquidation (`_calculateUserERC20Debt`), the result is never capped to the borrower’s actual debt in `debtAsset`. When `actualDebtToLiquidate` exceeds the borrower’s real balance in that asset, `_repayUserERC20Debt` burns only the real debt and returns a positive `remainDebtToLiquidate`, which is then credited to the borrower as new cross-mode supply via `erc20IncreaseCrossSupply`, while the liquidator still pays the full `actualDebtToLiquidate` through `erc20TransferInLiquidity`.
- Impact: A borrower with debt split across multiple assets can be liquidated on NFT collateral against one debt asset for more than they owe in that asset. The surplus is minted as free supply to the borrower at the liquidator’s expense, enabling value extraction from liquidators and bad protocol accounting.

## Isolate auction redeem debits wrong borrower account
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateRedeem`; `src/libraries/logic/ValidateLogic.sol` : `validateIsolateRedeemLoan`
- Mechanism: On redeem, scaled isolate debt is reduced with `VaultLogic.erc20DecreaseIsolateScaledBorrow(debtGroupData, params.msgSender, vars.amountScaled)`, but isolate borrows are recorded against the NFT owner (`onBehalf` in `executeIsolateBorrow`). Validation only checks loan status/asset, not that `msgSender` is the NFT owner. The per-loan `loanData.scaledAmount` is reduced for the victim’s NFT, while `userScaledIsolateBorrow[msgSender]` is reduced for the caller.
- Impact: Any third party with sufficient isolate scaled debt in the same group can call `executeIsolateRedeem` on someone else’s auctioned loan. They pay the redeem cost and reduce their own debt, while the victim’s loan state is mutated without reducing the victim’s aggregate isolate borrow balance. This corrupts debt accounting (orphaned user-level debt vs. per-loan records), can cancel auctions without the borrower paying, and may allow further borrows or repayment inconsistencies on the affected NFT.

## Yield borrow cap uses inflated total supply
- Location: `src/libraries/logic/YieldLogic.sol` : `executeYieldBorrowERC20` (staker cap branch)
- Mechanism: Both the asset-level and staker-level cap checks multiply `vars.totalSupply` (computed with the wrong index above) by `yieldCap` / `ymData.yieldCap`. Because `totalSupply` is overstated whenever `borrowIndex > supplyIndex`, both limits are simultaneously weakened.
- Impact: Compounds the first finding: privileged yield modules / staking integrations can progressively drain pool liquidity beyond intended uncollateralized exposure, leaving regular suppliers unable to withdraw.

