# Audit: 2024-07-benddao

## Yield Cap Miscalculation due to Wrong Index
- Location: `src/libraries/logic/YieldLogic.sol` : `executeYieldBorrowERC20`
- Mechanism: When calculating the total supply to enforce the asset-level yield cap, the function incorrectly passes `groupData.borrowIndex` to `VaultLogic.erc20GetTotalCrossSupply()` instead of the asset's supply index (e.g., `assetData.supplyIndex` or `InterestLogic.getNormalizedSupplyIncome(assetData)`). Because the borrow index accumulates interest faster than the supply index (due to utilization being < 100% and protocol fees), the calculated `totalSupply` is artificially inflated.
- Impact: The inflated total supply raises the effective yield cap, allowing whitelisted yield stakers to borrow more liquidity than the configured `yieldCap` percentage of the actual supply. This can lead to excessive borrowing, protocol insolvency, or liquidity drainage.

## Isolate Repay/Redeem Accounting Desync (Wrong Debt Holder)
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateRepay` & `executeIsolateRedeem`
- Mechanism: When repaying or redeeming an isolate loan, the protocol decreases the global isolate borrow balance (`userScaledIsolateBorrow`) of `params.onBehalf` or `params.msgSender`. However, it fails to verify that this address is the actual owner of the NFT (`tokenData.owner`), unlike `executeIsolateBorrow` and `executeIsolateLiquidate` which correctly use the NFT owner. 
- Impact: An attacker who has their own isolate debt can call `repay` or `redeem` on another user's NFT and specify themselves as the debt holder. The attacker pays the tokens and reduces their own global debt, while the victim's NFT-specific debt (`loanData.scaledAmount`) is reduced. The victim's global debt remains unchanged but becomes "orphaned" (no longer tied to the NFT's specific loan data). This breaks the accounting invariant between global user debt and specific NFT debt, allowing debt manipulation and incorrect liquidation/withdrawal states.
