# Audit: 2024-04-noya

## Flash loan contract can drain arbitrary connectors
- Location: `contracts/helpers/BaseConnector.sol` : `sendTokensToTrustedAddress`; `contracts/connectors/BalancerFlashLoan.sol` : `receiveFlashLoan`
- Mechanism: `BaseConnector.sendTokensToTrustedAddress` trusts any call from the registry-wide `flashLoan` address and transfers arbitrary `token`/`amount` to it. `BalancerFlashLoan.receiveFlashLoan` lets an authorized keeper execute arbitrary `destinationConnector.call(...)` calls, so the flash loan contract can be used as `msg.sender` against any connector, not only the connector/vault currently being flash-loaned.
- Impact: A keeper for one vault can make the shared flash-loan contract pull tokens from another vault’s connector, then forward them out through arbitrary calls, causing cross-vault asset theft.

## Zero-address queue entries can permanently block deposits and withdrawals
- Location: `contracts/accountingManager/AccountingManager.sol` : `deposit`, `withdraw`, `executeDeposit`, `executeWithdraw`
- Mechanism: `deposit` never checks `receiver != address(0)`, and `withdraw` never checks `receiver != address(0)` or `share > 0`. Queues are processed strictly FIFO. A queued deposit to the zero address reverts when `_mint` is reached; a queued withdrawal to the zero address can revert on `baseToken.safeTransfer`, including with zero shares for many ERC20s.
- Impact: An attacker can enqueue a bad request at the head of either queue and block all later deposits or withdrawals from executing.

## Morpho debt is counted as positive TVL
- Location: `contracts/connectors/MorphoBlueConnector.sol` : `_getPositionTVL`
- Mechanism: The connector computes TVL as `supplyAmount + borrowAmount + collateralValue`. Borrowed assets are liabilities and should be subtracted, not added. If borrowed loan tokens are also held or redeployed through token positions, the same borrowed value can be counted again elsewhere.
- Impact: Vault TVL and share price are overstated after Morpho borrowing, letting shareholders withdraw more than their fair claim and causing new depositors to receive too few shares.

## Synthetix collateral and debt are misaccounted
- Location: `contracts/connectors/SNXConnector.sol` : `_getPositionTVL`, `mintOrBurnSUSD`
- Mechanism: `_getPositionTVL` values `totalDeposited + totalAssigned`, even though assigned collateral is part of deposited collateral rather than an additional asset. `mintOrBurnSUSD` also registers minted sUSD as a token holding but `_getPositionTVL` never subtracts the corresponding Synthetix debt.
- Impact: SNX positions can materially overstate NAV, allowing inflated withdrawals, under-minting of depositor shares, and excessive performance fees.

## Uniswap V3 TVL counts global NFPM liquidity
- Location: `contracts/connectors/UNIv3Connector.sol` : `_getPositionTVL`
- Mechanism: The connector reads `pool.positions(keccak256(abi.encodePacked(positionManager, tickLower, tickUpper)))`. In Uniswap V3, that pool key belongs to the global NonfungiblePositionManager and aggregates all NFTs using the same pool/tick range, not the connector’s specific `tokenId`.
- Impact: Anyone can mint their own Uniswap V3 position with matching ticks to inflate the vault’s reported TVL, then exploit inflated withdrawal calculations or fee accounting.

## Aerodrome staked LP is omitted from TVL
- Location: `contracts/connectors/AerodromeConnector.sol` : `stake`, `_getPositionTVL`
- Mechanism: `stake` deposits LP tokens into the gauge, but `_getPositionTVL` only values `IERC20(pool).balanceOf(address(this))` and ignores `IGauge(gauge).balanceOf(address(this))`.
- Impact: After LP is staked, vault TVL is understated. Attackers can deposit while shares are underpriced and profit when the LP is unstaked or otherwise counted again.

## Balancer LP valuation uses the wrong supply denominator
- Location: `contracts/connectors/BalancerConnector.sol` : `_getPositionTVL`
- Mechanism: The connector divides by `IERC20(pool.pool).totalSupply()`. Balancer pools, especially composable/preminted BPT pools, require actual supply excluding preminted/self-held BPT. Using raw ERC20 total supply misprices the vault’s LP share.
- Impact: Balancer positions can be severely under- or over-valued, enabling unfair deposits, withdrawals, and fee calculations.

## Pendle market deposits can send surplus assets to treasury
- Location: `contracts/connectors/PendleConnector.sol` : `depositIntoMarket`
- Mechanism: The connector transfers SY and PT to the market, calls `market.mint`, then calls `market.skim()`. Pendle `skim` is not a refund-to-caller primitive; surplus tokens can be swept to Pendle’s treasury/recipient instead of back to the vault.
- Impact: Any imbalance between supplied SY/PT and the market’s used amounts can permanently lose vault funds.

## Pendle LP/PT rates are double-converted
- Location: `contracts/connectors/PendleConnector.sol` : `_getPositionTVL`
- Mechanism: `getLpToAssetRate` and `getPtToAssetRate` return asset-denominated rates, but the code adds those results into `SYAmount` and later multiplies the whole sum by `SY.exchangeRate()` again. This treats asset-denominated values as SY-denominated values.
- Impact: Pendle positions are mispriced, so users can deposit or withdraw against an incorrect share price.

## Dolomite borrow positions are never tracked
- Location: `contracts/connectors/Dolomite.sol` : `openBorrowPosition`, `closeBorrowPosition`
- Mechanism: `openBorrowPosition` calls `registry.updateHoldingPosition(..., true)`, where `true` means remove the position. As a result, opening a borrow position does not add the Dolomite borrow account to the holding registry.
- Impact: Dolomite liabilities/positions can be invisible to vault TVL, letting share accounting ignore debt and misprice deposits, withdrawals, and fees.

## Registry swap-delete corrupts moved position indexes
- Location: `contracts/accountingManager/Registry.sol` : `updateHoldingPosition`
- Mechanism: When removing a holding position, the registry swaps the last entry into the removed slot but rebuilds the moved entry’s index key with `calculatorConnector` instead of the owning connector address used in the original key. This is wrong for token-holding positions whose calculator is the accounting manager.
- Impact: The moved holding can become undiscoverable by `getHoldingPositionIndex`, allowing duplicate token positions to be added and the same connector token balance to be counted multiple times in TVL.

## Pending performance fees are not reserved before withdrawals
- Location: `contracts/accountingManager/AccountingManager.sol` : `recordProfitForFee`, `collectPerformanceFees`, `executeWithdraw`
- Mechanism: `recordProfitForFee` only stores `preformanceFeeSharesWaitingForDistribution`; it does not mint or otherwise reserve those shares before the 12-hour waiting period. Withdrawals during that window are calculated against an undiluted `totalSupply`.
- Impact: Shareholders can withdraw after profits are recorded but before fees are minted, avoiding their share of performance fees and shifting dilution to remaining users.

## Routed Chainlink prices return values with inconsistent decimals
- Location: `contracts/helpers/valueOracle/NoyaValueOracle.sol` : `_getValue`; `contracts/helpers/valueOracle/oracles/ChainlinkOracleConnector.sol` : `getValue`
- Mechanism: Multi-hop routes such as token → ETH → USD pass the intermediate ETH-denominated amount into an ETH/USD Chainlink conversion that returns USD scaled like the ETH input path, not like the final base token. The route logic also repeatedly calls `_getValue(asset, sources[i], ...)` instead of using the current `quotingToken`.
- Impact: Routed oracle prices can be off by large decimal factors, directly corrupting TVL, share pricing, withdrawal amounts, and fee calculations.

