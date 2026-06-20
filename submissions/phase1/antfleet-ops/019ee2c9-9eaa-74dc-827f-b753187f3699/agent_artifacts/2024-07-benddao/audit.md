# Audit: 2024-07-benddao

## Arbitrary caller can steal an auctioned NFT using the highest bidder’s escrow
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateLiquidate`
- Mechanism: `executeIsolateLiquidate` never verifies that `params.msgSender` is `loanData.lastBidder`. Once an auction has ended, any caller can invoke liquidation. The function consumes the stored `loanData.bidAmount` via `erc20TransferOutBidAmountToLiqudity`, optionally charges only any shortfall to the current caller, and then transfers the NFT to `params.msgSender`. It also sends any bid surplus to the borrower. Because the winning bidder’s funds are already escrowed from `executeIsolateAuction`, the finalization step is effectively permissionless but pays the wrong party.
- Impact: anyone, including the borrower, can finalize the auction and receive the NFT while the real highest bidder loses their locked bid. If the bid exceeds the debt, the borrower also pockets the excess.

## Whitelisted yield managers can freeze arbitrary isolated NFTs without owner approval
- Location: `src/libraries/logic/YieldLogic.sol` : `executeYieldSetERC721TokenData`
- Mechanism: the direct `Yield.yieldSetERC721TokenData` path only checks that the NFT is isolate-supplied, that the locker is unset or already equal to the caller, and that the caller has a nonzero configured yield cap on some debt asset. It does not verify that the caller owns the NFT or has been approved by its owner. A whitelisted manager can therefore set `lockerAddr` on any compatible NFT. Later, withdrawal and supply-mode changes require `lockerAddr == address(0)`, while isolate borrowing only accepts `lockerAddr == address(this)` or zero, so a manager lock makes the NFT unusable by its owner.
- Impact: any approved yield manager can arbitrarily lock users’ isolated NFTs and block withdrawals, supply-mode changes, and further borrowing until that manager unlocks them.

## Yield cap checks use the borrow index instead of the supply index
- Location: `src/libraries/logic/YieldLogic.sol` : `executeYieldBorrowERC20`
- Mechanism: the function computes `totalSupply` with `VaultLogic.erc20GetTotalCrossSupply(assetData, groupData.borrowIndex)`. Cross supply balances are scaled by `assetData.supplyIndex`, not by the group borrow index. As borrow interest accrues, `borrowIndex` can materially exceed `supplyIndex`, causing the code to overstate supply and therefore overstate both the asset-level and manager-level yield borrowing ceilings.
- Impact: a whitelisted yield manager can borrow substantially more than the configured `yieldCap`, extracting more unsecured liquidity than the protocol intends to allow.

## Chainlink prices remain valid forever after feed stoppage
- Location: `src/PriceOracle.sol` : `getAssetPriceFromChainlink`
- Mechanism: the oracle only checks `updatedAt != 0` and `answeredInRound >= roundId`. It never compares `updatedAt` against `block.timestamp` or any heartbeat threshold. A feed that has stopped updating but still has a historical round remains acceptable indefinitely, despite the code using `ORACLE_PRICE_IS_STALE` errors.
- Impact: if a Chainlink feed stalls during market movement, the protocol will continue using obsolete prices. Attackers can then borrow against stale-high collateral or liquidate against stale-low collateral, depending on the direction of the move.

