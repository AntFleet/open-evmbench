# Audit: 2024-07-munchables

## Pet rewards are scaled by 1e18 twice
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: `PET_TOTAL_SCHNIBBLES` is configured as an already 1e18-scaled amount, but `petterSchnibbles` and `pettedSchnibbles` multiply the split reward by `1e18` again.
- Impact: Any user who pets can mint astronomically more unfed schnibbles than intended, inflating game balances and downstream rewards.

## Snuggery maximum size can be bypassed
- Location: `src/managers/SnuggeryManager.sol` : `increaseSnuggerySize`
- Mechanism: The function only checks `previousSize >= MAX_SNUGGERY_SIZE` before adding `_quantity`; it never checks `previousSize + _quantity <= MAX_SNUGGERY_SIZE`.
- Impact: A player can buy a large `_quantity` once and exceed the global snuggery cap, allowing more imported NFTs and more chonk/reward capacity than intended.

## Munchadex bonus is applied retroactively on NFT receipt
- Location: `src/managers/MunchadexManager.sol` : `updateMunchadex`
- Mechanism: On transfer, the recipient’s Munchadex counters are increased before `accountManager.forceHarvest(_to)` is called. Harvest bonus calculations therefore use the newly received NFT set for the entire elapsed period since the recipient’s last harvest.
- Impact: Users can move NFTs between accounts just before harvest to apply collection bonuses retroactively and over-mint schnibbles.

## Social spray can mint unbounded schnibbles
- Location: `src/managers/AccountManager.sol` : `spraySchnibblesPropose` / `execSprayProposal`
- Mechanism: The proposal path caps only the number of recipients with `MAX_SCHNIBBLE_SPRAY`; it does not cap each `_schnibbles[i]` amount or the proposal total.
- Impact: A proposer plus approval role can credit arbitrary schnibble amounts to any accounts, bypassing the bounded `rewardSpray` path.

## Land plot moves leave stale plot ownership state
- Location: `src/managers/LandManager.sol` : `transferToUnoccupiedPlot`
- Mechanism: The function marks the old plot empty and the requested plot occupied, but never updates `toilerState[tokenId].plotId` to the new `plotId`.
- Impact: A renter can repeatedly move one staked NFT and leave multiple plots permanently marked occupied, denying other users access to a landlord’s plots and corrupting unstake/farming accounting.

## Invalid land plots continue farming after plot count drops
- Location: `src/managers/LandManager.sol` : `_farmPlots`
- Mechanism: The invalid-plot check uses `_getNumPlots(landlord) < _toiler.plotId`, but valid plot IDs are `0..numPlots-1`; the check should treat `plotId >= numPlots` as invalid.
- Impact: A renter in plot `0` can continue farming even after the landlord has zero plots, and other boundary plots can keep earning after the landlord unlocks enough funds to remove them.

## Negative land bonuses can brick staked NFTs
- Location: `src/managers/LandManager.sol` : `_farmPlots`
- Mechanism: Farming computes `uint256((int256(schnibblesTotal) + int256(schnibblesTotal) * finalBonus) / 100)`. For negative configured realm/rarity combinations, the signed result can become negative and the cast to `uint256` reverts.
- Impact: Any account with such a staked NFT cannot `farmPlots`, `unstakeMunchable`, or move plots because those paths all force farming first, trapping the NFT in the contract.

## Land manager reads economic parameters from wrong config keys
- Location: `src/managers/LandManager.sol` : `_reconfigure`
- Mechanism: `MIN_TAX_RATE`, `MAX_TAX_RATE`, `DEFAULT_TAX_RATE`, `BASE_SCHNIBBLE_RATE`, and `PRICE_PER_PLOT` are loaded from unrelated keys such as `StorageKey.LockManager`, `AccountManager`, and `NFTOverlord`.
- Impact: With normal configuration these values can be zero or nonsensical, causing division-by-zero plot calculations, broken tax bounds, or incorrect land reward emissions.

## Anyone can force Blast gas claims
- Location: `src/managers/RewardsManager.sol` : `claimGasFeeForContracts`
- Mechanism: The gas-claim function is public and has no `onlyRole`/authorization check, even though it claims gas for arbitrary supplied contracts through Blast.
- Impact: Any caller can prematurely claim gas fees from governed contracts to the distributor, potentially reducing time-dependent Blast gas rewards and disrupting treasury strategy.

## Point conversion appears to invert the configured rate
- Location: `src/managers/ClaimManager.sol` : `convertPointsToTokens`
- Mechanism: `_pointsPerToken` is named and configured as points-per-token, but the function mints `(_pointsToConvert * _pointsPerToken) / 1e12`, using it as a multiplier instead of a divisor.
- Impact: If configured as the name implies, users can mint far more MUNCH tokens than intended for their points.

