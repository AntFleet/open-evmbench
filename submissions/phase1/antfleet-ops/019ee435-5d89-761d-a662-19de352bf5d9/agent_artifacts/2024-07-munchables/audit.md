# Audit: 2024-07-munchables

## Petting mints 1e18 times too many schnibbles
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: `PET_TOTAL_SCHNIBBLES` is already configured as an 18-decimal amount, but `petterSchnibbles` and `pettedSchnibbles` multiply the split reward by `1e18` again: `((totalSchnibbles * 5) / 11) * 1e18`.
- Impact: Any user can repeatedly pet eligible NFTs to mint massively inflated unfed schnibbles, then feed/level assets far beyond the intended economy.

## Snuggery changes apply harvest bonuses retroactively
- Location: `src/managers/SnuggeryManager.sol` : `importMunchable`, `exportMunchable`
- Mechanism: Importing/exporting changes the snuggery data used by `BonusManager._calculateLevelBonus`, but these functions only force claim points, not `AccountManager.harvest`. A user can wait with old `lastHarvestDate`, import high-level/full-snuggery NFTs, then harvest as if that bonus existed for the entire elapsed period.
- Impact: Attackers can rotate valuable NFTs through accounts with locked funds and over-mint schnibbles from retroactive harvest bonuses.

## Munchadex transfers harvest after applying the new bonus
- Location: `src/managers/MunchadexManager.sol` : `updateMunchadex`
- Mechanism: On NFT transfer, the recipient’s Munchadex counters are incremented before `accountManager.forceHarvest(_to)` is called. The forced harvest therefore uses the post-transfer Munchadex bonus for time accrued before the recipient owned the NFT.
- Impact: A user can transfer collection-completing NFTs into an account just before harvest and receive inflated historical schnibbles.

## Snuggery size cap can be bypassed
- Location: `src/managers/SnuggeryManager.sol` : `increaseSnuggerySize`
- Mechanism: The function only checks `previousSize >= MAX_SNUGGERY_SIZE`; it never checks `previousSize + _quantity <= MAX_SNUGGERY_SIZE`.
- Impact: A user can buy a large `_quantity` in one call and exceed the global snuggery limit, enabling extra NFT slots and larger level/full-snuggery bonuses than intended.

## Land staking can lock in zero tax for legacy landlords
- Location: `src/managers/LandManager.sol` : `stakeMunchable`
- Mechanism: `stakeMunchable` does not require `plotMetadata[landlord]` to be initialized. If a landlord locked before metadata was triggered, `currentTaxRate` defaults to zero and is copied into `toilerState.latestTaxRate`.
- Impact: A renter can stake before the landlord initializes metadata and accrue farming rewards tax-free until the renter next farms, depriving the landlord of their intended share.

## Moving plots corrupts occupancy accounting
- Location: `src/managers/LandManager.sol` : `transferToUnoccupiedPlot`
- Mechanism: The function clears the old plot and marks the new plot occupied, but never updates `toilerState[tokenId].plotId` to the new `plotId`.
- Impact: Later farming/unstaking still references the old plot, which can clear another renter’s plot or leave the new plot permanently occupied, causing plot DoS and inconsistent land accounting.

## Removed plots can continue farming
- Location: `src/managers/LandManager.sol` : `_farmPlots`
- Mechanism: Invalid plot detection uses `_getNumPlots(landlord) < _toiler.plotId`, but valid plot IDs are `0..numPlots-1`; the check should treat `plotId == numPlots` as invalid.
- Impact: When a landlord’s available plots shrink, a renter in the removed highest-index plot can continue farming instead of being marked dirty and forced to move.

## Negative land bonuses can brick staked NFTs
- Location: `src/managers/LandManager.sol` : `_farmPlots`
- Mechanism: Farming computes `uint256((int256(base) + int256(base) * finalBonus) / 100)`. For negative bonuses below `-1`, the expression becomes negative and the cast to `uint256` reverts. Because `unstakeMunchable` and `transferToUnoccupiedPlot` both run `forceFarmPlots` first, the user cannot exit.
- Impact: A malicious renter can permanently occupy a landlord plot with a negatively matched NFT, and honest users can have staked NFTs stuck.

