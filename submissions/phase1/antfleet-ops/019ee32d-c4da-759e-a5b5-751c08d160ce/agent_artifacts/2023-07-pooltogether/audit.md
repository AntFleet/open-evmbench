# Audit: 2023-07-pooltogether

An audit of the PoolTogether V5 Vault smart contracts has revealed several security vulnerabilities, ranging from critical to low severity. The findings are compiled below:

## Silent Truncation in `_shares` Downcasting to `uint96` Leads to Vault Draining
- Location: `Vault.sol` : `_mint`, `_burn`, `_transfer`
- Mechanism: The vault delegates internal token accounting to the `TwabController` which uses `uint96` to track balances. In the internal functions `_mint`, `_burn`, and `_transfer`, the contract downcasts the `_shares` parameter from `uint256` to `uint96` (e.g., `_twabController.burn(_owner, uint96(_shares))`). In Solidity 0.8.x, explicit downcasting does not revert on overflow; instead, it silently truncates the higher bits. 
- Impact: A user who has accumulated a balance larger than `type(uint96).max` (via multiple legitimate deposits/mints) can withdraw or redeem their assets. During withdrawal, `_withdraw` calls `_burn` with their full share amount. The `_twabController.burn` call receives a truncated `uint96` amount, resulting in only a small fraction of their actual TWAB balance being burned, while they receive the full `uint256` asset amount. By repeating this process, an attacker can completely drain the vault of all its underlying assets.

## Irrecoverable Exchange Rate and Loss of Principal due to Exchange Rate Cap
- Location: `Vault.sol` : `_currentExchangeRate`
- Mechanism: The function `_currentExchangeRate()` is designed to cap the withdrawable assets at `_totalSupplyToAssets` to prevent the exchange rate from exceeding `_lastRecordedExchangeRate`. If the vault suffers any loss, `_currentExchangeRate()` drops below `_lastRecordedExchangeRate`. On the next mint/burn, `_updateExchangeRate()` is invoked, and `_lastRecordedExchangeRate` is updated to this new, lower value. Once `_lastRecordedExchangeRate` drops, `_totalSupplyToAssets` will also permanently decrease. If the vault is subsequently replenished (via a donation, positive rebasing of the yield vault, or manual recovery), any calculation of `_currentExchangeRate()` will be capped by the new, depressed `_totalSupplyToAssets`.
- Impact: The exchange rate of the vault is permanently locked/ratcheted down after a loss event. It can never recover back to `1:1`, even if the vault receives sufficient assets to be fully collaterized again. Any recovered funds above the depressed exchange rate will be incorrectly categorized as "excess yield" and liquidated, permanently depriving original depositors of their recovered principal.

## User Griefing and Disappeared Prize-Winning Eligibility via Arbitrary Force-Sponsorship
- Location: `Vault.sol` : `_sponsor`
- Mechanism: The `sponsor` and `sponsorWithPermit` functions allow anyone to deposit assets and delegate to the `SPONSORSHIP_ADDRESS` on behalf of a `_receiver` address. The internal `_sponsor` function checks if the `_receiver`'s delegate is the `SPONSORSHIP_ADDRESS`. If it is not, it automatically invokes `_twabController.sponsor(_receiver)` to force-delegate the receiver's TWAB to the sponsorship address. There is no access control or consent verification restricting who can trigger this delegation change for the `_receiver`.
- Impact: An attacker can call `sponsor` with `1 wei` of assets for any active depositor address. This forces the victim's delegation to `SPONSORSHIP_ADDRESS`, completely revoking their eligibility to win any future prizes in the PoolTogether pool without their consent. The victim remains excluded from prize draws until they notice and manually re-delegate their shares.

## DOS on Winner's Prize Claims via Reverting Hooks
- Location: `Vault.sol` : `_claimPrize` and `claimPrizes`
- Mechanism: Winners can set custom prize-claiming hooks using the `setHooks` function. The vault claimer calls `claimPrizes` in batch to claim prizes for multiple winners in a single transaction. Inside `_claimPrize`, the vault triggers the winner's custom hook contract via `hooks.implementation.beforeClaimPrize` and `afterClaimPrize`. If a winner configures a hook contract that intentionally reverts or runs out of gas, the execution fails.
- Impact: A malicious winner can block the entire claimer batch transaction. Since claimers/bots execute claims for dozens of users in batches to optimize gas, a single reverting hook will cause the whole transaction to revert, causing a Denial of Service (DOS). This disrupts the prize distribution for innocent winners and wastes gas.

## Division by Zero Bricks Liquidation when Yield Fee is 100%
- Location: `Vault.sol` : `liquidate()`
- Mechanism: The `_setYieldFeePercentage` function permits the owner to set the yield fee percentage up to `FEE_PRECISION` (1e9, representing 100%). Inside `liquidate()`, the yield fee balance is calculated using:
  `(_amountOut * FEE_PRECISION) / (FEE_PRECISION - _yieldFeePercentage) - _amountOut`
  If `_yieldFeePercentage` is set to exactly `FEE_PRECISION`, the denominator `FEE_PRECISION - _yieldFeePercentage` evaluates to `0`.
- Impact: Any attempt to liquidate the vault's yield will revert due to a division-by-zero error, permanently bricking the liquidation process of the vault until the owner changes the fee percentage.

## Unnecessary and Dangerous Infinite Allowance of Vault Asset to `LiquidationPair`
- Location: `Vault.sol` : `setLiquidationPair()`
- Mechanism: The `setLiquidationPair` function executes `_asset.safeApprove(address(liquidationPair_), type(uint256).max)`. However, during the liquidation process inside `Vault.sol::liquidate()`, the `liquidationPair` does not transfer or spend the underlying `_asset`. The liquidator pays the `prizeToken` to the `prizePool` and receives newly minted vault shares in return.
- Impact: Granting maximum allowance of the vault's underlying primary asset to an external `LiquidationPair` contract is a violation of the principle of least privilege. If the `LiquidationPair` contract is compromised or contains a security flaw, the entire underlying balance of the vault can be drained.
