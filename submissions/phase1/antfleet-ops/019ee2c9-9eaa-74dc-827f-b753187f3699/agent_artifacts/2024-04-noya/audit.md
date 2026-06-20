# Audit: 2024-04-noya

## Uniswap V3 LP valuation counts other users’ liquidity
- Location: [UNIv3Connector.sol](/Users/augstar/open-evmbench/audit_sources/2024-04-noya/contracts/connectors/UNIv3Connector.sol:127) : `_getPositionTVL` (also inherited by [PancakeswapConnector.sol](/Users/augstar/open-evmbench/audit_sources/2024-04-noya/contracts/connectors/PancakeswapConnector.sol:8))
- Mechanism: `_getPositionTVL` rebuilds the pool position with `pool.positions(keccak256(abi.encodePacked(positionManager, tL, tU)))`. In Uniswap V3-style pools, that key is scoped to the shared `NonfungiblePositionManager` owner plus tick range, so all NFTs minted through the manager at the same range are aggregated there. The code therefore values the aggregate liquidity and owed fees for every position at `(token0, token1, fee, tickLower, tickUpper)`, not the vault’s specific `tokenId`.
- Impact: a malicious or compromised manager can open a tiny NFT in a busy range and make vault TVL include third-party liquidity, inflating share price and enabling over-withdrawal, under-minting to new depositors, and bogus fee extraction.

## Morpho Blue borrows are treated as assets
- Location: [MorphoBlueConnector.sol](/Users/augstar/open-evmbench/audit_sources/2024-04-noya/contracts/connectors/MorphoBlueConnector.sol:118) : `_getPositionTVL`
- Mechanism: the connector computes TVL as `supplyAmount + borrowAmount + collateralValueInLoanToken`. `borrowAmount` is a liability, but it is added instead of subtracted. Every Morpho borrow therefore increases reported vault assets even when net equity is unchanged or worse.
- Impact: a manager can lever the vault to manufacture fake TVL/profit, causing users to transact at manipulated share prices and allowing performance fees to be minted against nonexistent gains.

## Registry compaction corrupts holding-position indexes
- Location: [Registry.sol](/Users/augstar/open-evmbench/audit_sources/2024-04-noya/contracts/accountingManager/Registry.sol:348) : `updateHoldingPosition`
- Mechanism: when removing a non-last holding position, the contract moves the last element into the freed slot, but rewrites `isPositionUsed` with `holdingPositions[positionIndex].calculatorConnector` instead of `ownerConnector`. All future lookups are keyed by owner connector, so the moved entry keeps a stale old index while the new mapping is written under the wrong key. Later updates/removals can revert out of bounds or operate on the wrong slot, leaving ghost positions in `holdingPositions`.
- Impact: after one position deletion, another live position can become impossible to update/remove correctly, causing persistent TVL corruption and potentially blocking unwinds or letting stale assets remain counted in vault accounting.

## Underfunded withdrawals are booked as fully paid, inflating profit and fees
- Location: [AccountingManager.sol](/Users/augstar/open-evmbench/audit_sources/2024-04-noya/contracts/accountingManager/AccountingManager.sol:370) : `fulfillCurrentWithdrawGroup`; [AccountingManager.sol](/Users/augstar/open-evmbench/audit_sources/2024-04-noya/contracts/accountingManager/AccountingManager.sol:396) : `executeWithdraw`; [AccountingManager.sol](/Users/augstar/open-evmbench/audit_sources/2024-04-noya/contracts/accountingManager/AccountingManager.sol:582) : `getProfit`
- Mechanism: `fulfillCurrentWithdrawGroup` explicitly allows `totalABAmount < totalCBAmountFullfilled`, so withdrawals can be paid pro rata. But `executeWithdraw` adds `data.amount` to `processedBaseTokenAmount` and later `totalWithdrawnAmount`, even though the user only receives `data.amount * totalABAmount / totalCBAmountFullfilled` minus fee. The unpaid shortfall is thus accounted as if it left the vault, and `getProfit()` then overstates profit; `recordProfitForFee` / `collectPerformanceFees` can monetize that fake profit.
- Impact: after a loss or liquidity shortfall, remaining holders can be diluted by performance fees on losses that were never recovered, and the vault’s accounting no longer reflects real asset balances.

## Aerodrome gauge-staked LP disappears from TVL
- Location: [AerodromeConnector.sol](/Users/augstar/open-evmbench/audit_sources/2024-04-noya/contracts/connectors/AerodromeConnector.sol:100) : `stake`; [AerodromeConnector.sol](/Users/augstar/open-evmbench/audit_sources/2024-04-noya/contracts/connectors/AerodromeConnector.sol:125) : `_getPositionTVL`
- Mechanism: `stake` deposits LP into the gauge, but `_getPositionTVL` only values `IERC20(pool).balanceOf(address(this))` and ignores `IGauge(gauge).balanceOf(address(this))`. Once LP is staked, the registry still says the position exists, but vault TVL stops counting the bulk of its value.
- Impact: any user can deposit while the position is staked and shares are underpriced, then redeem later against the true asset base, extracting value from existing holders.

## Maverick partial removals unregister still-live liquidity
- Location: [MaverickConnector.sol](/Users/augstar/open-evmbench/audit_sources/2024-04-noya/contracts/connectors/MaverickConnector.sol:115) : `removeLiquidityFromMaverickPool`
- Mechanism: after removing liquidity from one Maverick `tokenId`, the connector always calls `registry.updateHoldingPosition(..., true)` and deletes the pool’s holding position unconditionally. That happens even if the NFT still has residual liquidity or the vault owns other Maverick tokenIds for the same pool. Since `_getPositionTVL` values all tokenIds held for the pool, deleting the registry entry drops remaining live liquidity out of TVL.
- Impact: a normal partial rebalance can make real Maverick assets vanish from accounting, letting new depositors mint too many shares and later withdraw against value that was never actually removed.

## Pendle can unregister a market while Penpie-staked LP is still live
- Location: [PendleConnector.sol](/Users/augstar/open-evmbench/audit_sources/2024-04-noya/contracts/connectors/PendleConnector.sol:216) : `decreasePosition`; [PendleConnector.sol](/Users/augstar/open-evmbench/audit_sources/2024-04-noya/contracts/connectors/PendleConnector.sol:303) : `isMarketEmpty`
- Mechanism: `isMarketEmpty` checks SY/PT/YT balances and direct `market.balanceOf(address(this))`, but ignores `pendleMarketDepositHelper.balance(market, address(this))`. `_getPositionTVL` does count Penpie-staked LP, so `decreasePosition(..., closePosition=true)` can delete the registry entry for a market even though the vault still holds value there through Penpie.
- Impact: live Pendle assets can be dropped from TVL, enabling underpriced deposits and later value extraction once the market is re-registered or the staked LP is withdrawn.

