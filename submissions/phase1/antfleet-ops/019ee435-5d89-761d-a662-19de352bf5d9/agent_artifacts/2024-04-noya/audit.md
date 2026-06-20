# Audit: 2024-04-noya

## Zero-address deposits can brick the deposit queue
- Location: `contracts/accountingManager/AccountingManager.sol` : `deposit`, `executeDeposit`
- Mechanism: `deposit(receiver, amount, referrer)` does not reject `receiver == address(0)`. The request is queued, but `executeDeposit` later calls `_mint(data.receiver, data.shares)`, which reverts for the zero address. Because the queue is strictly FIFO and the reverting request is never deleted or skipped, `depositQueue.first` cannot advance.
- Impact: Anyone can deposit a nonzero amount with `receiver = address(0)` and permanently block execution of that deposit and all later deposits behind it.

## Invalid withdrawal requests can brick withdrawals
- Location: `contracts/accountingManager/AccountingManager.sol` : `withdraw`, `executeWithdraw`
- Mechanism: `withdraw` accepts both `share == 0` and `receiver == address(0)`. A zero-share-only withdraw group sets `totalCBAmountFullfilled` to zero, causing division by zero in `executeWithdraw`. A zero-address receiver can also make the base token transfer revert. The queue has no cancellation or skip path once such a request is in the active group.
- Impact: Any address can enqueue a zero-share withdrawal, or a shareholder can withdraw to the zero address, causing withdrawal execution to revert indefinitely and blocking later users’ withdrawals.

## Withdrawal groups can be marked fulfilled without receiving the requested assets
- Location: `contracts/accountingManager/AccountingManager.sol` : `retrieveTokensForWithdraw`, `fulfillCurrentWithdrawGroup`, `executeWithdraw`
- Mechanism: `retrieveTokensForWithdraw` adds `retrieveData[i].withdrawAmount` to `amountAskedForWithdraw` even when the connector returns and transfers a smaller `amount`. The balance check only verifies that the returned amount arrived. `fulfillCurrentWithdrawGroup` then uses the requested amount to decide readiness, while `executeWithdraw` burns all queued shares and pays only pro-rata from the actually available balance.
- Impact: Underfunded retrieval can burn users’ full shares for partial payment. It also records `data.amount` rather than the amount actually paid in `totalWithdrawnAmount`, inflating profit accounting and enabling excessive performance-fee minting.

## Morpho debt is counted as a positive asset
- Location: `contracts/connectors/MorphoBlueConnector.sol` : `_getPositionTVL`
- Mechanism: The Morpho TVL calculation adds `borrowAmount` to `supplyAmount + collateralValue` instead of subtracting it as a liability. Borrowed loan tokens may also be tracked separately as held tokens through `_updateTokenInRegistry`, compounding the overstatement.
- Impact: The vault can be materially overvalued after Morpho borrowing. Depositors receive too few shares, withdrawers and fee receivers can extract value from other users, and performance fees can be minted on nonexistent profit.

## SNX minted USD debt is omitted from TVL
- Location: `contracts/connectors/SNXConnector.sol` : `mintOrBurnSUSD`, `_getPositionTVL`
- Mechanism: `mintOrBurnSUSD` can mint protocol USD debt against collateral, but `_getPositionTVL` only returns the value of deposited/assigned collateral and never subtracts the minted USD liability. The minted USD token is also added to the registry as a held token when present.
- Impact: SNX positions are overvalued by their outstanding debt. Share pricing, withdrawals, and fee calculations can all treat borrowed value as equity.

## Uniswap V3 / PancakeSwap TVL reads global NPM liquidity, not the vault NFT
- Location: `contracts/connectors/UNIv3Connector.sol` : `_getPositionTVL`; `contracts/connectors/PancakeswapConnector.sol` : inherited `_getPositionTVL`
- Mechanism: The TVL code decodes the vault’s `tokenId` but does not use that NFT’s liquidity. Instead it queries `pool.positions(keccak256(abi.encodePacked(positionManager, tickLower, tickUpper)))`, which is the aggregate pool position owned by the global NonfungiblePositionManager for that tick range, including unrelated LP NFTs from other users.
- Impact: A tiny vault NFT in a popular range can be valued as if the vault owned all NPM liquidity in that range. This can massively inflate vault TVL and enable value extraction through deposits, withdrawals, or performance fees.

## Aerodrome gauge-staked LP is invisible to TVL
- Location: `contracts/connectors/AerodromeConnector.sol` : `stake`, `_getPositionTVL`
- Mechanism: `stake` deposits LP tokens into the gauge, but `_getPositionTVL` only values `IERC20(pool).balanceOf(address(this))` and ignores `IGauge(gauge).balanceOf(address(this))`.
- Impact: After staking, the vault’s Aerodrome LP position can be reported as zero. New depositors can mint shares at an artificially low price and later profit when the LP is unstaked or otherwise made visible again.

## Registry removal corrupts holding-position indexes
- Location: `contracts/accountingManager/Registry.sol` : `updateHoldingPosition`
- Mechanism: Holding positions are indexed by `keccak256(abi.encode(ownerConnector, positionId, data))`, but when removing an item and moving the last array element into its slot, the registry rewrites the moved element’s index using `calculatorConnector` instead of `ownerConnector`. Future lookups by the real owner connector return stale indexes.
- Impact: Position removals can corrupt the registry, causing positions to be unremovable, duplicated, or allowing later removals to pop an unrelated last position. Since TVL is derived from this registry, assets or debts can be omitted or double-counted, mispricing vault shares.

## Maverick partial removal drops the whole pool position from accounting
- Location: `contracts/connectors/MaverickConnector.sol` : `removeLiquidityFromMaverickPool`
- Mechanism: After any `removeLiquidity` call, the connector unconditionally removes the Maverick pool holding position from the registry. It does not check whether the NFT still has liquidity or whether the connector has other Maverick NFTs in the same pool.
- Impact: Remaining Maverick liquidity can disappear from TVL. Attackers can deposit while the vault is underpriced and withdraw after the position is restored or assets are otherwise realized.

## Lido withdrawal requests overwrite each other in the registry
- Location: `contracts/connectors/LidoConnector.sol` : `requestWithdrawals`, `claimWithdrawal`
- Mechanism: All Lido withdrawal NFTs share one constant position id. A second request updates the existing holding position rather than adding a separate one, and the registry update path only changes `additionalData`, not the stored request id. Claiming one request can remove the shared accounting entry while other withdrawal NFTs remain outstanding.
- Impact: Pending Lido withdrawals can be undercounted or left stale in TVL, allowing share-price manipulation around deposits and withdrawals.

## Pendle Penpie-staked LP can be removed from accounting
- Location: `contracts/connectors/PendleConnector.sol` : `decreasePosition`, `isMarketEmpty`
- Mechanism: `decreasePosition(..., closePosition=true)` removes the Pendle position if local SY/PT/YT/market balances are zero, but `isMarketEmpty` ignores LP staked in Penpie via `pendleMarketDepositHelper.balance`.
- Impact: Staked Pendle LP can remain economically owned by the vault while being removed from TVL, letting users mint shares against an artificially low vault value.

## Pending deposits bypass the total deposit cap
- Location: `contracts/accountingManager/AccountingManager.sol` : `deposit`, `TVL`
- Mechanism: `TVL()` subtracts `depositQueue.totalAWFDeposit`, so already queued but unexecuted deposits are excluded from the total-limit check. During a new deposit, only the current transfer is effectively counted before `totalAWFDeposit` is incremented.
- Impact: Users can queue many deposits before execution and push final vault assets far above `depositLimitTotalAmount`, bypassing the configured risk cap.

