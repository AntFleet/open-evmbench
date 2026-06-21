# Audit: 2024-04-noya

# Open EVMBench Detect Audit — Noya (2024-04-noya)

## Uniswap V3 TVL uses global NPM liquidity instead of vault NFT liquidity
- Location: `UNIv3Connector.sol` : `_getPositionTVL`
- Mechanism: TVL is derived from `pool.positions(keccak256(abi.encodePacked(positionManager, tickLower, tickUpper)))`, which returns the **aggregate** liquidity the NonfungiblePositionManager holds at that tick range across **all** NFTs system-wide. It never reads `positionManager.positions(tokenId)` for the vault’s specific NFT. Any third-party LP at the same ticks is counted as vault TVL.
- Impact: Vault TVL can be massively overstated. Share pricing (`previewDeposit` / `previewRedeem`), deposit minting, withdraw sizing, and performance-fee profit calculations are skewed. An attacker can deposit when TVL is inflated and redeem after correction, or existing withdrawers can extract more than their fair share at the expense of remaining LPs.

## Morpho Blue TVL adds borrow exposure instead of subtracting it
- Location: `MorphoBlueConnector.sol` : `_getPositionTVL`
- Mechanism: Net position value is computed as `supplyAmount + borrowAmount + collateralValue`, but borrowed assets are a liability. The correct net is `supplyAmount + collateralValue - borrowAmount` (or equivalent debt-adjusted formula).
- Impact: Any Morpho borrow position inflates reported TVL. Share price is overstated, so withdrawers redeem more base token than the vault actually holds, draining value from remaining depositors. Performance fees can also be taken on fictitious profit.

## Withdraw accounting records full calculated amounts while users receive pro-rata less
- Location: `AccountingManager.sol` : `executeWithdraw`
- Mechanism: When a withdraw group is under-funded, users are paid `data.amount * totalABAmount / totalCBAmountFullfilled` (pro-rata haircut), but `totalWithdrawnAmount` is incremented by the full `data.amount` for each request. `getProfit()` uses `TVL + totalWithdrawnAmount - totalDepositedAmount`, so withdrawn liabilities are overstated whenever `totalABAmount < totalCBAmountFullfilled`.
- Impact: Reported profit is artificially lowered after partial fulfillments, or the accounting mismatch can be exploited across withdraw cycles to skew performance-fee calculations and vault P&L tracking. Remaining shareholders absorb the gap between recorded withdrawals and tokens actually sent.

## Dolomite borrow positions are never registered for TVL tracking
- Location: `DolomiteConnector.sol` : `openBorrowPosition`
- Mechanism: After opening a borrow account, `updateHoldingPosition` is called with `removePosition = true` and `data = abi.encode(accountId)`. For a new borrow account, `isPositionUsed[holdingPositionId]` is `0`, so the registry call returns early without adding the borrow account. Only the default deposit account (`abi.encode(0)`) is tracked from `deposit()`.
- Impact: Collateral and debt on non-default Dolomite accounts are excluded from `TVL()`. TVL is understated while real assets/liabilities exist off-registry, causing depositors to receive too many shares and enabling value extraction by withdrawing against an understated share price.

## Aerodrome staked LP is omitted from TVL
- Location: `AerodromeConnector.sol` : `_getPositionTVL`
- Mechanism: TVL only counts `IERC20(pool).balanceOf(address(this))`. LP moved to a gauge via `stake()` is held by the gauge contract and is not included in the balance check.
- Impact: After staking, vault TVL drops sharply for Aerodrome positions. New depositors mint shares at an artificially low price; existing shareholders are diluted. Conversely, unstaking before valuation can temporarily inflate TVL for manipulators coordinating with the deposit queue timing.

## Prisma TVL reverts when trove is underwater, bricking vault valuation
- Location: `PrismaConnector.sol` : `_getPositionTVL`
- Mechanism: TVL is computed as `_getValue(collateral, ...) - _getValue(debt, ...)` with no guard when debt value exceeds collateral. In Solidity 0.8 this underflows and reverts.
- Impact: Any underwater Prisma trove causes `TVL()` (and therefore `totalAssets()`, deposit share calculation, withdraw calculation, and fee logic) to revert. Deposits, withdrawals, and fee collection can be frozen (denial of service) until the position is made solvent or removed.

## SNX V3 TVL ignores minted debt
- Location: `SNXV3Connector.sol` : `_getPositionTVL`
- Mechanism: TVL is `_getValue(collateralType, base, totalDeposited + totalAssigned)` and does not subtract sUSD (or other) debt from `mintUsd` operations via `mintOrBurnSUSD`.
- Impact: Leveraged SNX positions overstate net equity in TVL. Share price is inflated; withdrawers can extract more than the vault’s true net position, leaving remaining LPs with bad debt.

## Gearbox TVL uses `address(840)` as a USD stand-in for oracle conversion
- Location: `GearBoxV3.sol` : `_getPositionTVL`
- Mechanism: Net USD equity from Gearbox (`totalValueUSD - totalDebtUSD`) is passed to `_getValue(address(840), base, amount)`. `address(840)` is not a meaningful ERC-20 on deployed chains; the value oracle is asked to price a nonsense token address.
- Impact: Gearbox positions contribute incorrect (often zero or wildly wrong) values to TVL. Share pricing for Gearbox-heavy vaults is unreliable, enabling mispriced deposits/withdrawals and incorrect fee accrual.

## Pendle TVL relies on manipulable 10-second oracle windows
- Location: `PendleConnector.sol` : `_getPositionTVL`
- Mechanism: LP and PT conversions use `getLpToAssetRate(10)` and `getPtToAssetRate(10)` — a 10-second TWAP/window that can be moved with short-lived pool trades or flash-loan manipulation.
- Impact: An attacker can temporarily inflate or deflate Pendle position TVL around `calculateDepositShares` / `calculateWithdrawShares` boundaries (gated by `TVLHelper.getLatestUpdateTime`), minting too many shares or redeeming at too favorable a rate.

## `onlyVaultMaintainer` modifier logic is inverted
- Location: `Registry.sol` : `onlyVaultMaintainer`
- Mechanism: The modifier reverts when `msg.sender != maintainer || !hasRole(EMERGENCY_ROLE, msg.sender)`. By De Morgan’s law, it only passes when the caller is **both** the vault maintainer **and** holds the global `EMERGENCY_ROLE`. The governor and emergency-only paths use the correct `&&` pattern; this one uses `||`.
- Impact: Timelocked vault maintainers cannot call `addConnector`, `removeTrustedPosition`, `updateConnectorTrustedTokens`, etc., unless they also hold the global emergency role. Governance operations are blocked or must be routed through emergency keys, breaking intended access separation and potentially forcing privileged recovery paths.

## PancakeSwap connector inherits Uniswap V3 TVL flaw and adds MasterChef blind spot
- Location: `PancakeswapConnector.sol` : (inherits `UNIv3Connector._getPositionTVL`)
- Mechanism: Inherits the global-NPM-liquidity TVL bug above. Additionally, when positions are transferred to MasterChef via `sendPositionToMasterChef`, valuation still goes through the broken `_getPositionTVL` path and does not account for MasterChef custody or staking rewards in TVL.
- Impact: Same share-price distortion as the Uniswap V3 issue, compounded for Pancake positions that are staked. Deposit/withdraw fairness and fee accounting are unreliable for PancakeSwap strategies.

## Performance-fee shares can be griefed via public TVL drop check
- Location: `AccountingManager.sol` : `checkIfTVLHasDroped`
- Mechanism: Anyone can call this function. If `getProfit()` falls below `storedProfitForFee` (even briefly from oracle noise, market moves, or a short-term TVL manipulation), it zeroes `preformanceFeeSharesWaitingForDistribution` and resets `profitStoredTime`.
- Impact: An attacker can grief the strategy manager’s accrued performance fee between `recordProfitForFee` and `collectPerformanceFees` (which requires a 12–48 hour window), forcing fee forfeiture without stealing user principal directly. Combined with manipulable connector TVL or oracle reads, this becomes a practical MEV/griefing vector.

