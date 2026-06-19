# Audit: 2024-07-benddao

## Yield debt shares can be diluted across pools
- Location: `src/yield/YieldStakingBase.sol` : `convertToDebtShares`, `convertToDebtAssets`, `_stake`, `_repay`
- Mechanism: `totalDebtShare` is global for the whole staking contract, but `getTotalDebt(poolId)` is pool-specific. Because `stake()` accepts an arbitrary `poolId`, borrowing in a second pool with little or no existing debt can mint a huge number of debt shares against the global denominator. That dilutes existing positions in other pools, making `_getNftDebtInUnderlyingAsset()` report far less debt than those NFTs actually created.
- Impact: A user can make prior positions appear almost debt-free, repay only a small amount, unlock their NFT, and leave the staking contract with unassigned pool debt.

## Isolate repayments can corrupt another user’s loan
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateRepay`
- Mechanism: Repayment validates only that the target `loanData` is active and uses the requested reserve asset. It never checks that `params.onBehalf` is the owner of the NFT loan. The function decreases isolate debt for `params.onBehalf`, but mutates and can delete `loanData` for `params.nftTokenIds`.
- Impact: A borrower can repay their own isolate debt while deleting or reducing another user’s NFT loan record. The victim’s NFT can become withdrawable while their debt accounting remains orphaned, creating bad debt and inconsistent pool state.

## Isolate auction redeem is not restricted to the NFT borrower
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateRedeem`
- Mechanism: Redeem does not check that `params.msgSender` owns the auctioned NFT. It decreases isolate debt for `params.msgSender`, then reduces the target NFT’s `loanData.scaledAmount` and returns the loan to active status.
- Impact: Any address with isolate debt in the same asset/group can cancel or partially cancel another borrower’s auction using its own repayment path, corrupting debt attribution and potentially preventing liquidation of undercollateralized NFTs.

## Bot-forced yield unstake/repay uses the bot’s account instead of the position account
- Location: `src/yield/YieldStakingBase.sol` : `_unstake`, `_repay`; `src/yield/lido/YieldEthStakingLido.sol` / `src/yield/etherfi/YieldEthStakingEtherfi.sol` : `protocolRequestWithdrawal`, `protocolClaimWithdraw`
- Mechanism: `_unstake` and derived protocol hooks resolve the yield account from `yieldAccounts[msg.sender]`. When `botAdmin` triggers an unhealthy position, `msg.sender` is the bot, not the NFT owner, while the actual stake is stored in `sd.yieldAccount`.
- Impact: Forced liquidation/unwind of unhealthy yield positions reverts or operates on the wrong yield account. Undercollateralized yield positions can become unenforceable, allowing bad debt to accumulate.

## Yield borrow caps use the borrow index as the supply index
- Location: `src/libraries/logic/YieldLogic.sol` : `executeYieldBorrowERC20`
- Mechanism: The yield cap denominator is computed as `VaultLogic.erc20GetTotalCrossSupply(assetData, groupData.borrowIndex)`. Cross supply must be normalized with `assetData.supplyIndex`, not the yield group’s `borrowIndex`. As borrow interest accrues, the borrow index can diverge from the supply index and inflate the computed supply base.
- Impact: Whitelisted yield managers can borrow more than the configured asset-level and manager-level caps, increasing uncollateralized protocol exposure beyond risk limits.

## ERC20 flash loan repayment is not verified by balance accounting
- Location: `src/libraries/logic/FlashLoanLogic.sol` : `executeFlashLoanERC20`; `src/libraries/logic/VaultLogic.sol` : `erc20TransferInOnFlashLoan`
- Mechanism: ERC20 flash loans transfer assets out and later call `safeTransferFrom(receiver, address(this), amount)` without checking the pool’s balance before and after repayment. Other ERC20 liquidity paths enforce exact balance deltas, but flash loan repayment does not.
- Impact: If a listed flash-loan-enabled token is fee-on-transfer, rebasing, or otherwise non-standard, the pool can receive less than the borrowed amount while the flash loan succeeds, leaving accounting overstated and liquidity missing.

## Borrow caps are checked against stale interest indexes
- Location: `src/libraries/logic/BorrowLogic.sol` : `executeCrossBorrowERC20`; `src/libraries/logic/ValidateLogic.sol` : `validateCrossBorrowERC20Basic`
- Mechanism: Cross-borrow validation checks `borrowCap` before `InterestLogic.updateInterestIndexs()` is called. The cap calculation uses stored borrow indexes, so accrued interest since the last update is ignored during the cap check.
- Impact: Borrowers can open new cross-borrows even when the current debt including accrued interest should already exceed the asset borrow cap.

## Chainlink prices can be indefinitely stale
- Location: `src/PriceOracle.sol` : `getAssetPriceFromChainlink`
- Mechanism: The oracle checks `answer > 0`, `updatedAt != 0`, and `answeredInRound >= roundId`, but it never enforces a maximum age or heartbeat for `updatedAt`.
- Impact: If a Chainlink feed stalls, borrowing and liquidation continue using obsolete prices. Attackers can borrow against overpriced collateral or avoid liquidation until the feed updates.

## Chainlink feed decimals are not normalized
- Location: `src/PriceOracle.sol` : `getAssetPriceFromChainlink`
- Mechanism: The oracle returns the raw Chainlink `answer` without scaling it to `BASE_CURRENCY_UNIT`. The rest of the protocol assumes all asset prices share one base unit.
- Impact: Any configured feed whose decimals differ from the assumed base unit will be mispriced, allowing overborrowing, incorrect liquidations, or underpriced debt.

## ERC721 delegations persist after collateral ownership changes
- Location: `src/libraries/logic/PoolLogic.sol` : `executeDelegateERC721`; `src/libraries/logic/VaultLogic.sol` : `erc721DecreaseCrossSupply`, `erc721TransferCrossSupply`, `erc721DecreaseIsolateSupply`, `erc721TransferIsolateSupplyOnLiquidate`
- Mechanism: Users can delegate rights for pool-held NFTs through Delegate Registry V2, but the protocol never revokes those delegations when the NFT is withdrawn, liquidated, or transferred to a new internal owner.
- Impact: A previous depositor’s delegate can retain active rights when the same NFT is later held by the pool for a different owner, enabling theft or griefing of delegated NFT benefits such as claims, airdrops, or gated actions.

