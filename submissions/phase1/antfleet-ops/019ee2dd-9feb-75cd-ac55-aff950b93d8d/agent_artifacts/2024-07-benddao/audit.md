# Audit: 2024-07-benddao

 ## Flash-Loan ERC20 Callback Lacks Reentrancy Guard
- Location: `src/modules/FlashLoan.sol` : `flashLoanERC20`
- Mechanism: `PoolManager.dispatch()` is decorated with the no-op `reentrantOK` modifier, so the protocol relies on individual module functions to acquire the `reentrancyLock` via `nonReentrant`. `flashLoanERC721` correctly uses `nonReentrant`, but `flashLoanERC20` deliberately omits it (the comment says “Don’t use nonReentrant modifier here”). During the ERC20 flash loan the tokens are transferred to the receiver and `executeOperationERC20` is invoked while `reentrancyLock` remains `UNLOCKED`, so a malicious receiver can reenter every other state-changing module function (deposit, borrow, withdraw, liquidate, yield borrow, etc.) in the same transaction.
- Impact: A malicious flash-loan receiver can break the protocol’s reentrancy assumptions, call protected operations during the callback window, and potentially combine the callback with price/oracle/state manipulations to extract value or corrupt accounting.

## Yield Borrow Cap Computed With Borrow Index Instead of Supply Index
- Location: `src/libraries/logic/YieldLogic.sol` : `executeYieldBorrowERC20`
- Mechanism: The asset-level and staker-level yield caps are supposed to limit yield borrowing to a percentage of total supply. The code calculates `vars.totalSupply = VaultLogic.erc20GetTotalCrossSupply(assetData, groupData.borrowIndex)`, passing the group borrow index rather than `assetData.supplyIndex`. Because borrow and supply indices diverge over time, the cap is computed from the wrong base and can become significantly larger or smaller than intended.
- Impact: Yield stakers can borrow more than the configured percentage of real supply when the borrow index exceeds the supply index, diluting regular suppliers and potentially draining pool liquidity beyond the intended cap.

## Yield Staking Repay Uses the Wrong Yield Account for Bot-Admin Liquidations
- Location: `src/yield/YieldStakingBase.sol` : `_repay`
- Mechanism: The function allows either the NFT owner or the `botAdmin` to call `repay`. It resolves the yield account with `vars.yieldAccout = IYieldAccount(yieldAccounts[msg.sender])`, i.e. the caller’s account, instead of `sd.yieldAccount` which stores the NFT owner’s account that was used during staking. All subsequent operations (computing `withdrawAmount`, updating `accountYieldInWithdraws`, subtracting `accountYieldShares`, etc.) are therefore applied to the wrong account when `msg.sender == botAdmin`.
- Impact: Bot-admin liquidations/repayments are broken; the bot’s own yield account balance may be consumed or the transaction may revert, leaving underwater yield positions un-liquidatable. If the bot account holds funds, those funds could be incorrectly debited.

## Unstake Fine Is Locked in the Contract and `totalUnstakeFine` Is Never Reduced
- Location: `src/yield/YieldStakingBase.sol` : `_unstake`, `_repay`
- Mechanism: In `_unstake` the bot-admin can set `sd.unstakeFine` and the global `totalUnstakeFine` is incremented. In `_repay` the borrower is charged `vars.nftDebtWithFine = vars.nftDebt + sd.unstakeFine`, but the fine portion is never transferred to the first bidder, the protocol treasury, or any other recipient, and `totalUnstakeFine` is never decremented.
- Impact: Unstake fine amounts are permanently locked in the yield staking contract with no recovery mechanism, and `totalUnstakeFine` becomes a permanently increasing, meaningless accounting value.

## Native ETH Wrapper Functions Require WETH Approval and Debit the Wrong Party
- Location: `src/libraries/logic/VaultLogic.sol` : `wrapNativeTokenInWallet`, `unwrapNativeTokenInWallet`; callers include `BVault.depositERC20`, `BVault.withdrawERC20`, `CrossLending.crossBorrowERC20`, `CrossLending.crossRepayERC20`, `CrossLiquidation.crossLiquidateERC20`, `IsolateLending.isolateBorrow/isolateRepay`, `IsolateLiquidation.isolateAuction/isolateRedeem/isolateLiquidate`, `YieldEthStakingEtherfi.repayETH`, `YieldEthStakingLido.repayETH`
- Mechanism: `wrapNativeTokenInWallet` deposits ETH into WETH and then transfers the WETH to `user`; the caller then pulls it back from `user` with `safeTransferFrom`, requiring the user to have pre-approved WETH spending. `unwrapNativeTokenInWallet` likewise pulls WETH from `user` before unwrapping. For operations like `crossBorrowERC20`/`withdrawERC20`, the WETH is first sent to the `receiver`, but the subsequent unwrap debits `msgSender`, not `receiver`, so when `receiver != msgSender` the caller pays with their own WETH while the recipient receives WETH.
- Impact: Native-token paths are effectively non-functional unless users pre-approve WETH; moreover, borrow/withdraw/liquidate with ETH can debit the wrong wallet and cause unexpected losses or reverts.

## Off-by-One Asset and Group Cap Checks
- Location: `src/libraries/logic/ConfigureLogic.sol` : `executeAddAssetERC20`, `executeAddAssetERC721`, `executeAddPoolGroup`
- Mechanism: The cap checks use `<=` instead of `<`. For example, `executeAddAssetERC20` checks `poolData.assetList.length() <= Constants.MAX_NUMBER_OF_ASSET` before adding the asset, so when the list already contains `MAX_NUMBER_OF_ASSET` elements the new asset is still accepted, resulting in `MAX_NUMBER_OF_ASSET + 1` assets. The same pattern exists for `executeAddPoolGroup` with `MAX_NUMBER_OF_GROUP`.
- Impact: The protocol can be configured with one more asset/group than the documented maximum, which can break downstream invariants and gas assumptions in view and state-changing loops.

## PriceOracle Missing Chainlink Safeguards
- Location: `src/PriceOracle.sol` : `getAssetPriceFromChainlink`
- Mechanism: The Chainlink price lookup verifies `answer > 0`, `updatedAt != 0`, and `answeredInRound >= roundId`, but it does not check the aggregator’s `minAnswer`/`maxAnswer` circuit-breaker bounds, does not verify the sequencer is up on L2s, and does not enforce a maximum staleness threshold.
- Impact: Stale, frozen, or bounded-but-wrong prices can be consumed, causing unfair liquidations, allowing over-borrowing against under-collateralized positions, or preventing legitimate liquidations.
