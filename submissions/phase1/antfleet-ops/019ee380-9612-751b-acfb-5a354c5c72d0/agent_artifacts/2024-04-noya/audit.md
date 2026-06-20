# Audit: 2024-04-noya

Below are the genuine security vulnerabilities I found. I've focused on logic/accounting/oracle flaws that are exploitable, not style.

## MorphoBlue position TVL adds debt instead of subtracting it
- Location: `contracts/connectors/MorphoBlueConnector.sol` : `_getPositionTVL`
- Mechanism: For a Morpho position the connector computes
  `tvl = _getValue(loanToken, base, supplyAmount + borrowAmount + convertCToL(collateral,...))`.
  `borrowAmount` (derived from `pos.borrowShares`) is the vault's **debt**, a liability, and must be *subtracted*. Every other lending connector in the codebase does this correctly (Compound `positiveBalance - negativeBalance`, Frax/Silo/Dolomite/Prisma all subtract debt). Here the debt is added to the asset side, so the position value is overstated by `2 × borrowAmount`.
- Impact: `AccountingManager.totalAssets()`/`TVL()` is fed by the sum of connector `_getPositionTVL`s, and share price = `totalAssets / totalSupply`. By borrowing against a Morpho position the manager (or anyone able to influence a Morpho position the vault holds) inflates the reported NAV. An attacker who deposits before the inflation and redeems after (via the deposit/withdraw queues, both of which price shares off this TVL with `previewDeposit`/`previewRedeem`) extracts value from other holders; conversely it mis-mints/burns fee shares (`recordProfitForFee` uses `getProfit = TVL + withdrawn - deposited`). This is a direct NAV-manipulation / fund-loss bug.

## Uniswap V3 position TVL reads the aggregate NPM position, not the vault's
- Location: `contracts/connectors/UNIv3Connector.sol` : `_getPositionTVL`
- Mechanism: Instead of using the per-NFT liquidity (`positionManager.positions(tokenId)`, as `getCurrentLiquidity` does), the TVL path recomputes liquidity from the pool: `key = keccak256(abi.encodePacked(positionManager, tL, tU)); pool.positions(key)`. In Uniswap V3 a pool position is keyed by `(owner, tickLower, tickUpper)`, and for all NonfungiblePositionManager-minted NFTs the `owner` is the NPM contract. Therefore `pool.positions(key)` returns the **sum of every NPM user's liquidity** in that exact tick range, plus their aggregate `tokensOwed0/1`, not just this vault's position.
- Impact: Whenever any third party holds liquidity in the same pool/tick range through the NPM, the vault's reported TVL is inflated by that foreign liquidity. The inflation is attacker-controllable (mint a large NPM position in the vault's tick range), again translating into manipulable share pricing for deposits/withdrawals.

## LP position valuation uses spot AMM reserves (flash-loan manipulable)
- Location: `contracts/connectors/AerodromeConnector.sol` : `_getPositionTVL`; `contracts/connectors/CamelotConnector.sol` : `_getPositionTVL`
- Mechanism: Both value an LP position by taking the pool's *current* reserves (`IPool.getReserves()` / `ICamelotPair.getReserves()`), splitting them by `balance/totalSupply`, and pricing each leg via `valueOracle`. Because the per-token reserve split is read at spot, an attacker can imbalance the pool with a swap/flash loan before the TVL read: the oracle prices stay "true" while the reserves are skewed, so the summed value of the LP's share is inflated (for a constant-product pool the value is minimized at the true ratio and grows as reserves are pushed away from it).
- Impact: Within a single transaction an attacker can inflate the connector's reported TVL, which feeds `AccountingManager.TVL()` and thus `previewDeposit`/`previewRedeem`. Combined with the deposit/withdraw queues this allows minting shares cheaply or redeeming them at an inflated price. A fair-reserve (oracle-derived) LP valuation should be used instead of raw `getReserves()`.

## Withdraw group can be permanently bricked because fulfillment requires retrieving the full CB amount
- Location: `contracts/accountingManager/AccountingManager.sol` : `fulfillCurrentWithdrawGroup` / `retrieveTokensForWithdraw`
- Mechanism: `retrieveTokensForWithdraw` caps the amount that can be pulled from connectors per call to `neededAssetsForWithdraw() = totalCBAmount - availableAssets` (`if (amountAskedForWithdraw_temp > neededAssets) revert`), so `amountAskedForWithdraw` can only ever accumulate up to `totalCBAmount - availableAssets`. But `fulfillCurrentWithdrawGroup` requires `amountAskedForWithdraw == currentWithdrawGroup.totalCBAmount` whenever `neededAssets != 0`. If the contract holds *any* non-pending base-token balance at group time (`availableAssets > 0`), the equality can never be reached because the retrievable amount is strictly less than `totalCBAmount`.
- Impact: The withdraw group gets stuck in the started-but-not-fulfilled state. Because `calculateWithdrawShares` reverts while a group is active and unfulfilled (`NoyaAccounting_ThereIsAnActiveWithdrawGroup`) and a new group can't be started, this is a liveness/DoS on all queued withdrawals until the available balance happens to be exactly zero.

The first two (Morpho debt sign, UNIv3 aggregate liquidity) are the highest-impact and most clear-cut: both directly and controllably inflate the vault NAV that all deposit/withdraw and fee accounting is priced against.

