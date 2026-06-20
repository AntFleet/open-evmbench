# Audit: 2024-04-noya

## Global flash-loan trust lets one vault reach other vault connectors
- Location: `contracts/connectors/BalancerFlashLoan.sol` : `receiveFlashLoan`; `contracts/helpers/BaseConnector.sol` : `sendTokensToTrustedAddress`
- Mechanism: `BalancerFlashLoan` is stored once in the registry and `BaseConnector.sendTokensToTrustedAddress` trusts `msg.sender == registry.flashLoan()` without checking that the call is for the same vault or that the destination connector belongs to the flash-loan user’s vault. During `receiveFlashLoan`, arbitrary `destinationConnector` calls are executed as the global flash-loan contract.
- Impact: A keeper or compromised keeper for one vault can make calls as the trusted global flash-loan address against connectors of other vaults and pull tokens out of them.

## Malformed queue entries can permanently block deposits or withdrawals
- Location: `contracts/accountingManager/AccountingManager.sol` : `deposit`, `withdraw`, `executeDeposit`, `executeWithdraw`
- Mechanism: Deposits do not reject `receiver == address(0)`, and withdrawals do not reject `receiver == address(0)` or `share == 0`. The queues are strict FIFO and have no cancellation/skip path. A zero deposit receiver later reverts at `_mint(address(0), shares)`. A zero-share withdrawal can create a fulfilled group with `totalCBAmountFullfilled == 0`, causing division by zero in `executeWithdraw`.
- Impact: Any user can enqueue a poisoned request that makes later queue execution revert, freezing all subsequent deposits or withdrawals behind it.

## Direct token donations manipulate queued deposit share pricing
- Location: `contracts/accountingManager/AccountingManager.sol` : `deposit`, `calculateDepositShares`, `TVL`
- Mechanism: Deposit shares are calculated later with `previewDeposit(data.amount)`, and `TVL()` includes raw `baseToken.balanceOf(address(this))` minus only queued deposits. Direct transfers to the accounting manager are therefore treated as vault assets immediately, even though they are not associated with any deposit request and users have no `minSharesOut` protection.
- Impact: An existing shareholder can donate base tokens before queued deposits are calculated to inflate share price and make victims receive fewer shares. Donations can also push TVL over the deposit cap and block new deposits.

## Performance-fee shares are not reserved before user withdrawals
- Location: `contracts/accountingManager/AccountingManager.sol` : `recordProfitForFee`, `collectPerformanceFees`
- Mechanism: `recordProfitForFee` records pending fee shares in `preformanceFeeSharesWaitingForDistribution` but does not mint or otherwise reserve them until after the 12-hour lock. During that window, `totalSupply()` excludes the pending dilution, so withdrawals are priced as if fee shares did not exist.
- Impact: Users can withdraw after profit is recorded but before fees are minted, escaping their share of performance-fee dilution and shifting the cost to remaining vault holders.

## Registry removal corrupts moved holding-position indexes
- Location: `contracts/accountingManager/Registry.sol` : `updateHoldingPosition`
- Mechanism: Holding positions are keyed by `keccak256(ownerConnector, positionId, data)` when inserted. When removing a position and swapping the last entry into the deleted slot, the registry rewrites the moved entry’s index using `calculatorConnector` instead of the original owner connector. For positions where these differ, the canonical key is left stale.
- Impact: Existing positions can become undiscoverable or duplicated in the registry, causing TVL to omit assets or keep stale positions, which corrupts share pricing for deposits and withdrawals.

## Maintainer-only registry functions are effectively locked
- Location: `contracts/accountingManager/Registry.sol` : `onlyVaultMaintainer`
- Mechanism: The modifier reverts when `msg.sender != maintainer || hasRole(EMERGENCY_ROLE, msg.sender) == false`, which requires the caller to be both the vault maintainer and an emergency-role holder. The neighboring modifiers use the intended OR-style authorization.
- Impact: Normal maintainers cannot add/remove connectors or trusted positions unless they also hold the emergency role, freezing critical security administration such as removing a malicious connector.

## Routed oracle pricing uses the wrong hop asset
- Location: `contracts/helpers/valueOracle/NoyaValueOracle.sol` : `_getValue`
- Mechanism: Multi-hop pricing updates `quotingToken` each iteration but calls `_getValue(asset, sources[i], initialValue)` instead of `_getValue(quotingToken, sources[i], initialValue)`. Each hop therefore prices the original asset against the next source token rather than pricing the previous hop’s output.
- Impact: Any asset configured with a routed oracle path can be severely mispriced, corrupting vault TVL and allowing deposits or withdrawals at unfair share prices.

## Chainlink route decimals can mis-scale ETH/USD conversions
- Location: `contracts/helpers/valueOracle/oracles/ChainlinkOracleConnector.sol` : `getValue`, `getValueFromChainlinkFeed`
- Mechanism: The connector derives token units from `decimalsSource`, but for ETH/USD sentinel routes it can fall back to feed-address decimals handling instead of the true source/output token decimals. Combined with inverse routing, amounts can be returned in the wrong unit scale.
- Impact: Assets routed through ETH/USD Chainlink feeds can be over- or under-valued by large decimal factors, enabling unfair minting or redemption of vault shares.

## Morpho debt is counted as an asset
- Location: `contracts/connectors/MorphoBlueConnector.sol` : `_getPositionTVL`
- Mechanism: The Morpho TVL calculation adds `borrowAmount` to `supplyAmount` and collateral value instead of subtracting borrow liabilities. Debt therefore increases reported vault assets.
- Impact: Borrow-heavy Morpho positions inflate vault TVL, letting withdrawing shareholders redeem more base assets than their fair value and diluting later depositors.

## Synthetix collateral and debt are misaccounted
- Location: `contracts/connectors/SNXConnector.sol` : `_getPositionTVL`, `mintOrBurnSUSD`
- Mechanism: `_getPositionTVL` values `totalDeposited + totalAssigned`, even though assigned collateral is part of the deposited collateral set, and it does not subtract minted sUSD debt. Minted sUSD may also be counted as a held token elsewhere.
- Impact: SNX positions can be materially overvalued, allowing users to mint or redeem vault shares against inflated NAV.

## Uniswap V3 TVL reads global tick-range liquidity instead of the vault NFT
- Location: `contracts/connectors/UNIv3Connector.sol` : `_getPositionTVL`
- Mechanism: The connector decodes a `tokenId` but does not use it to read the NFT position. Instead it builds a pool `positions` key from the position manager address and ticks, which represents aggregate liquidity for that owner/tick range, not the specific vault NFT.
- Impact: Liquidity belonging to other NFTs with the same tick range can be counted as vault assets, inflating TVL and enabling unfair share issuance or redemption.

## Aerodrome staked LP is omitted from TVL
- Location: `contracts/connectors/AerodromeConnector.sol` : `stake`, `_getPositionTVL`
- Mechanism: `stake` deposits LP tokens into the gauge, but `_getPositionTVL` only reads `IERC20(pool).balanceOf(address(this))`. It does not include LP tokens staked in the gauge.
- Impact: Once LP is staked, the vault underreports assets. New depositors can receive too many shares, or remaining shareholders can be diluted.

## Balancer LP valuation uses raw totalSupply
- Location: `contracts/connectors/BalancerConnector.sol` : `_getPositionTVL`
- Mechanism: The Balancer connector divides by `IERC20(pool.pool).totalSupply()`. For Balancer pools with preminted or protocol-held BPT, raw ERC20 supply is not the circulating/actual supply that backs pool assets.
- Impact: Balancer positions can be under- or over-valued, causing incorrect vault share pricing.

## Pendle market mint can strand or lose surplus inputs
- Location: `contracts/connectors/PendleConnector.sol` : `depositIntoMarket`
- Mechanism: The connector transfers desired SY/PT amounts to the market and calls `market.mint`, then calls `market.skim()` as if it refunds unused surplus. Because no receiver is specified, surplus token handling is delegated to the market, not explicitly returned to the connector.
- Impact: Excess SY/PT sent during minting can be swept away or left outside vault accounting, causing direct loss or mispricing of vault assets.

## Pendle PT/LP valuation double-converts rates
- Location: `contracts/connectors/PendleConnector.sol` : `_getPositionTVL`
- Mechanism: The connector adds LP and PT values using `getLpToAssetRate` / `getPtToAssetRate`, then treats the accumulated amount as SY and multiplies it by `SY.exchangeRate()` again. If those oracle rates are already asset-denominated, the exchange rate is applied twice.
- Impact: Pendle positions can be systematically mispriced, allowing users to enter or exit the vault at an unfair share price.

## Penpie-staked Pendle LP can be removed from TVL
- Location: `contracts/connectors/PendleConnector.sol` : `decreasePosition`, `isMarketEmpty`
- Mechanism: `decreasePosition` removes the holding when `isMarketEmpty(market)` is true, but `isMarketEmpty` checks only direct SY/PT/YT/LP balances and ignores LP staked through `pendleMarketDepositHelper.balance(market, address(this))`.
- Impact: A vault can still own staked Pendle LP while the registry position is removed, making TVL omit those assets and misprice deposits/withdrawals.

## Dolomite borrow positions are immediately untracked
- Location: `contracts/connectors/Dolomite.sol` : `openBorrowPosition`
- Mechanism: After opening a borrow account, the connector calls `registry.updateHoldingPosition(..., true)`. The final `true` is the remove flag, so the newly opened Dolomite position is removed from the registry instead of added.
- Impact: Dolomite collateral and debt are excluded from vault TVL, corrupting NAV and share pricing.

## Underwater debt positions can revert all vault accounting
- Location: `contracts/connectors/AaveConnector.sol`, `CompoundConnector.sol`, `Dolomite.sol`, `PrismaConnector.sol`, `SiloConnector.sol` : `_getPositionTVL`
- Mechanism: Several debt connectors compute net value with unsigned subtraction such as `collateral - debt`. If the position becomes underwater, the subtraction reverts. `TVLHelper.getTVL` does not isolate connector failures, so one reverting position makes `AccountingManager.TVL()` revert.
- Impact: A bad debt or manipulated debt valuation can freeze deposits, withdrawals, fee accounting, and any other path that reads vault TVL.

## Maverick LP can be removed from TVL while liquidity remains
- Location: `contracts/connectors/MaverickConnector.sol` : `removeLiquidityFromMaverickPool`
- Mechanism: Maverick stores one registry holding per pool, while TVL aggregates all token IDs for that pool. `removeLiquidityFromMaverickPool` unconditionally removes the registry position after removing liquidity for a single token ID, without checking whether other token IDs or remaining bin liquidity still exist.
- Impact: Remaining Maverick liquidity can be omitted from vault TVL, allowing deposits at an artificially low price and diluting existing holders.

## Claimed Maverick rewards are not registered
- Location: `contracts/connectors/MaverickConnector.sol` : `claimBoostedPositionRewards`
- Mechanism: The function claims reward tokens but does not call `_updateTokenInRegistry` for the received reward assets, unlike other reward-harvesting connectors in the codebase.
- Impact: Claimed rewards can sit in the connector without being included in TVL, underpricing the vault and enabling unfair share minting.

