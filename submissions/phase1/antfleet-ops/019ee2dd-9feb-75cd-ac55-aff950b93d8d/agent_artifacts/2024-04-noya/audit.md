# Audit: 2024-04-noya

 ## Registry governance modifiers require BOTH roles instead of either
- **Location:** `contracts/accountingManager/Registry.sol` : `onlyVaultMaintainer`, `onlyVaultMaintainerWithoutTimeLock`, `onlyVaultGoverner`
- **Mechanism:** The modifiers use `||` where `&&` is intended. The condition `if (msg.sender != maintainer || !hasRole(EMERGENCY_ROLE, msg.sender)) revert;` only succeeds when the caller is **both** the maintainer/governor **and** holds the emergency role. The intended logic is to allow either the vault maintainer/governor or the emergency role to act.
- **Impact:** `addConnector`, `addTrustedPosition`, `removeTrustedPosition`, `updateConnectorTrustedTokens`, and `changeVaultAddresses` are effectively bricked unless the emergency address and maintainer/governor address are the same. A vault cannot add new connectors or positions, freeze/pause its positions, or update governance addresses, leading to a denial of service of vault maintenance.

## AccountingManager records inflated `totalWithdrawnAmount` on under-funded withdraws
- **Location:** `contracts/accountingManager/AccountingManager.sol` : `executeWithdraw`
- **Mechanism:** When a withdraw group is under-funded (`currentWithdrawGroup.totalABAmount < currentWithdrawGroup.totalCBAmountFullfilled`), each user receives `data.amount * totalABAmount / totalCBAmountFullfilled`, which is less than `data.amount`. However, `processedBaseTokenAmount += data.amount` and later `totalWithdrawnAmount += processedBaseTokenAmount` use the full pre-pro-rata `data.amount`.
- **Impact:** `totalWithdrawnAmount` is overstated, inflating `getProfit()` (`TVL + totalWithdrawn - totalDeposited`). This causes `recordProfitForFee` to compute excess performance fees and mint more performance-fee shares than the vault actually earned, stealing value from depositors.

## MorphoBlue connector adds borrow debt to TVL instead of subtracting
- **Location:** `contracts/connectors/MorphoBlueConnector.sol` : `_getPositionTVL`
- **Mechanism:** The function computes `borrowAmount` from `pos.borrowShares` but then adds it to the position value: `supplyAmount + borrowAmount + convertCToL(pos.collateral, ...)`. Borrowed assets should reduce, not increase, the net position value.
- **Impact:** Every MorphoBlue borrow position overstates the vault's TVL by twice the borrow amount. Since `AccountingManager.totalAssets()` returns `TVL()`, share price, deposit share calculations, withdraw base-token amounts, and performance/management fees are all computed from an inflated NAV, allowing value extraction.

## SNX V3 connector ignores minted sUSD debt in TVL
- **Location:** `contracts/connectors/SNXConnector.sol` : `_getPositionTVL`
- **Mechanism:** `_getPositionTVL` returns the full value of `totalDeposited + totalAssigned` collateral but never subtracts sUSD debt minted via `mintOrBurnSUSD`. The connector tracks the sUSD token in the registry but does not account for the corresponding liability.
- **Impact:** The vault NAV is inflated whenever sUSD is minted against SNX collateral. Deposit share prices, withdraw conversions, and fee calculations all become incorrect, enabling depositors/withdrawers to extract value at the expense of the pool.

## Aerodrome connector loses TVL for staked LP positions
- **Location:** `contracts/connectors/AerodromeConnector.sol` : `_getPositionTVL` (and `stake`/`unstake`)
- **Mechanism:** `_getPositionTVL` values the position solely from `IERC20(pool).balanceOf(address(this))`. The `stake` function deposits the LP token into an Aerodrome gauge, leaving the connector's pool-LP balance at zero. There is no accounting for gauge-held LP.
- **Impact:** Staking an Aerodrome LP position makes its TVL drop to zero, depressing the vault share price. Unstaking later causes a sudden NAV spike. This predictable price discontinuity can be exploited by depositing just before staking and withdrawing just before unstaking.

## Dolomite borrow positions are never added to holding positions
- **Location:** `contracts/connectors/Dolomite.sol` : `openBorrowPosition`
- **Mechanism:** `openBorrowPosition` calls `registry.updateHoldingPosition(..., abi.encode(accountId), "", true)`, where the final `true` is `removePosition`. Because the borrow account uses `accountId > 0` while the deposit account uses `accountId == 0`, no holding position is ever recorded for the borrowed funds.
- **Impact:** Assets borrowed into Dolomite sub-accounts are invisible to `TVLHelper.getTVL`, which only iterates recorded holding positions. The vault's share price and profit calculations therefore ignore borrowed assets, leading to incorrect deposit/withdraw pricing.

## Multiple connectors use manipulable spot prices for NAV
- **Location:** 
  - `contracts/connectors/UNIv3Connector.sol` : `_getPositionTVL` (`pool.slot0()`)
  - `contracts/connectors/AerodromeConnector.sol` : `_getPositionTVL` (`pool.getReserves()`)
  - `contracts/connectors/CamelotConnector.sol` : `_getPositionTVL` (`pair.getReserves()`)
  - `contracts/connectors/BalancerConnector.sol` : `_getPositionTVL` (`getPoolTokens`)
- **Mechanism:** These connectors read instantaneous reserves or slot-0 prices directly from DEX pools to compute position TVL. Such spot values can be manipulated via flash-loan swaps within a single block, especially because the vault's deposit/withdraw share calculations are tied to `AccountingManager.TVL()`.
- **Impact:** An attacker can temporarily distort the vault NAV to mint excess shares on deposit or receive inflated base-token amounts on withdraw. While the manager queues deposits/withdraws and uses `oldestUpdateTime`, the TVL is still derived from these unprotected spot readings.

## Prisma connector fails to update collateral token registry on collateral changes
- **Location:** `contracts/connectors/PrismaConnector.sol` : `addColl`, `adjustTrove`
- **Mechanism:** `addColl` deposits collateral into a Prisma trove but never calls `_updateTokenInRegistry(collateral)`. Likewise, `adjustTrove` can withdraw collateral (`wAmount > 0`) but only updates the debt token registry. The registry's generic token holdings can therefore remain stale.
- **Impact:** The collateral token may continue to be counted as a vault holding after it has been moved into Prisma, or fail to be removed after withdrawal, causing the generic token portion of `TVL()` to be overstated or understated.

## Compound connector checks token trust after withdrawal
- **Location:** `contracts/connectors/CompoundConnector.sol` : `withdrawOrBorrow`
- **Mechanism:** The function executes `IComet(_market).withdraw(asset, amount)` before verifying `registry.isTokenTrusted(vaultId, asset, address(this))`. The trust check is performed after the external call.
- **Impact:** Although the caller is the manager, this ordering allows an untrusted token to be withdrawn/borrowed from Compound before the check reverts the transaction. In a compromised-manager or governance-error scenario, untrusted tokens can be introduced into the vault's token holdings.
