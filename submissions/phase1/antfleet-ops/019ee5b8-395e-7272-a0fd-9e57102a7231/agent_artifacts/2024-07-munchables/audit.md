# Audit: 2024-07-munchables

Findings below are limited to genuine exploitable/security-relevant issues in the pasted code.

## Pet rewards are multiplied by 1e18 twice
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: `PET_TOTAL_SCHNIBBLES` is already treated as an 18-decimal amount, but `pet()` computes `petterSchnibbles` and `pettedSchnibbles` and then multiplies each by `1e18` again. This credits rewards that are `1e18` times larger than configured.
- Impact: Any user can repeatedly pet eligible NFTs and mint astronomically large unfed schnibbles to themselves and the target account, breaking the game economy and downstream feeding/level/points accounting.

## Negative land farming bonuses can underflow into massive rewards or freeze exits
- Location: `src/managers/LandManager.sol` : `_farmPlots`
- Mechanism: The farming calculation combines signed realm/rarity bonuses with `schnibblesTotal`, then casts the signed result to `uint256` without clamping. If `finalBonus` is sufficiently negative, the signed total becomes negative and converts to a near-`2^256` value. With nonzero tax this can instead overflow and revert.
- Impact: A renter with a negative-bonus setup can receive an enormous schnibble credit, or can cause farming to revert. Because `unstakeMunchable()` and plot transfer paths force farming first, the reverting case can trap staked NFTs and prevent users from exiting.

## Moving to an unoccupied plot leaves stale toiler state
- Location: `src/managers/LandManager.sol` : `transferToUnoccupiedPlot`
- Mechanism: The function updates occupancy for the old and new plots, but does not update `toilerState[tokenId].plotId`, does not clear `dirty`, and does not reset `lastToilDate`. The accounting state therefore continues to reference the previous plot even though the occupancy map marks a different plot as occupied.
- Impact: Users can permanently corrupt plot occupancy, leave plots falsely occupied, continue farming against the wrong plot metadata, or keep a moved NFT marked dirty so it can no longer farm correctly. This can deny service to landlords/renters and strand plot capacity.

## Invalid plot IDs remain farmable after landlord capacity shrinks
- Location: `src/managers/LandManager.sol` : `_farmPlots`
- Mechanism: Plot validity is checked with `_getNumPlots(landlord) < _toiler.plotId`. Plot IDs are zero-indexed, so the invalid condition should include equality. If a landlord shrinks from `N + 1` plots to `N`, a renter in plot `N` is now outside the valid range, but the check does not mark it dirty.
- Impact: Renters can continue earning from plots that no longer exist after the landlord reduces lock capacity, diluting rewards and bypassing the intended land-capacity constraint.

## Snuggery size cap can be bypassed
- Location: `src/managers/SnuggeryManager.sol` : `increaseSnuggerySize`
- Mechanism: The function only checks whether the current `maxSnuggerySize` is already at or above `MAX_SNUGGERY_SIZE`; it never checks whether `previousSize + _quantity` exceeds the cap.
- Impact: A player can buy multiple slots in one call and raise their snuggery above the configured maximum, allowing more NFTs, more chonk, and higher rewards than intended.

## Snuggery bonus changes apply retroactively to harvests
- Location: `src/managers/SnuggeryManager.sol` : `importMunchable`, `exportMunchable`, `feed`
- Mechanism: These functions can change the caller’s harvest bonus through snuggery composition, NFT levels, and full-snuggery status, but they do not force `AccountManager.harvest()` before changing that state. `AccountManager._harvest()` later applies the current bonus to the entire elapsed period since `lastHarvestDate`.
- Impact: A user can wait a long time, then import/feed/rearrange NFTs to maximize bonuses immediately before harvesting, receiving boosted schnibbles for time during which they did not actually satisfy the bonus conditions.

## Munchadex bonuses apply retroactively on NFT transfers
- Location: `src/managers/MunchadexManager.sol` : `updateMunchadex`
- Mechanism: Munchadex counters are updated before `accountManager.forceHarvest()` is called. Since harvest uses the current bonus state over the full time since the previous harvest, the recipient gets the newly increased Munchadex bonus retroactively, while the sender’s reduced state can also be applied to the prior accrual window.
- Impact: Players can transfer NFTs immediately before harvesting to claim bonus rewards for periods where they did not hold the required collection state, extracting unearned schnibbles.

## Referral bonuses are minted outside the period budget
- Location: `src/managers/ClaimManager.sol` : `_claimPoints`
- Mechanism: When a player has a referrer, `_claimPoints()` credits `_referralBonus` directly to `_points[player.referrer]`, but only the claimant’s `claimAmount` is added to `currentPeriod.claimed`. The referral bonus is not deducted from `currentPeriod.available` or accounted as claimed.
- Impact: Users can register accounts with controlled referrer addresses and mint additional points beyond the configured per-period distribution, inflating total claims and diluting the token economy.

## Migration can burn or migrate NFTs no longer owned by the snapshot user
- Location: `src/managers/MigrationManager.sol` : `_migrateNFTs`, `burnNFTs`, `burnRemainingPurchasedNFTs`
- Mechanism: Migration eligibility is based only on snapshot entries keyed by the original `_user` and `tokenId`. Before burning the old NFT and minting/crediting the new benefit, the contract does not verify that `_user` still owns the old NFT. `OldMunchNFT.burn()` authorizes the migration manager to burn any token.
- Impact: A snapshot owner can transfer or sell an old NFT after the snapshot and still migrate or burn it later, destroying the current holder’s NFT while minting the new NFT or points to themselves.

## Mixed-token migration totals are settled using only one token type
- Location: `src/managers/MigrationManager.sol` : `loadMigrationSnapshot`, `lockFundsForAllMigration`
- Mechanism: `loadMigrationSnapshot()` aggregates all locked migration amounts into one `totalLockedAmount` while overwriting `tokenLocked` with each entry’s token. `lockFundsForAllMigration()` then collects the entire aggregate in only the final stored token type, rather than tracking totals per token.
- Impact: If a user’s snapshot contains multiple locked token types, they can satisfy the full migration with only the last token recorded for them. This can underpay the required collateral and lock the wrong asset amount.

## NFT blacklist does not prevent blacklisted recipients
- Location: `src/tokens/MunchNFT.sol` : `_update`
- Mechanism: The transfer hook blocks transfers only when `from` is blacklisted or the token is blacklisted. It never checks whether `_to` is blacklisted.
- Impact: A blacklisted address can still receive NFTs from another account or through minting paths, bypassing the intended sanctions/containment mechanism.

