# Audit: 2024-07-munchables

## Mixed-collateral migrations can be settled with a single token type
- Location: `src/managers/MigrationManager.sol` : `loadMigrationSnapshot`, `lockFundsForAllMigration`, `_migrateNFTs`
- Mechanism: `loadMigrationSnapshot()` aggregates every locked NFT's `lockAmount` into `_userLockedAmounts[_user].totalLockedAmount`, but it overwrites `_userLockedAmounts[_user].tokenLocked` on each entry instead of enforcing a single collateral token per user. Later, `lockFundsForAllMigration()` collects the full aggregated amount only in that one final `tokenLocked`, and `_migrateNFTs()` re-locks only that asset in `LockManager`. Since `LockManager` supports multiple token types, a user with legacy positions across ETH/USDB/WETH can migrate the whole set while replacing the original basket with whichever token happened to be stored last.
- Impact: users can undercollateralize migration and substitute cheaper or different collateral for higher-value historical locks, extracting value from the protocol.

## Anyone can force-complete another user's full migration
- Location: `src/managers/MigrationManager.sol` : `migrateAllNFTs`
- Mechanism: once a user has called `lockFundsForAllMigration()` and `_userLockedAction[user]` becomes `LOCKED_FULL_MIGRATION`, `migrateAllNFTs(user, skip)` has no authorization check tying `msg.sender` to `user`. Any external account can trigger `_migrateNFTs()`, which marks snapshots claimed, burns the user's old NFTs, mints replacement NFTs, and locks the migrated funds on the user's behalf.
- Impact: a third party can unilaterally destroy a victim's old NFTs and force them into the migrated state at an attacker-chosen time.

## Munchadex bonuses are applied retroactively to the whole harvest window
- Location: `src/managers/MunchadexManager.sol` : `updateMunchadex`
- Mechanism: `updateMunchadex()` mutates the sender's or recipient's unique-species counters first, then calls `accountManager.forceHarvest()`. `AccountManager._harvest()` calculates rewards for the entire elapsed period since `lastHarvestDate` using the current `BonusManager.getHarvestBonus()`, which includes `_calculateMunchadexBonus()`. That means receiving a new unique species, or minting one, boosts the account's past accrual instead of only future accrual.
- Impact: attackers can move or mint unique NFTs into a high-value account immediately before a harvest-triggering action and overclaim schnibbles as if that account had held the Munchadex bonus for the full period.

## Petting over-mints schnibbles by 18 decimals
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: `PET_TOTAL_SCHNIBBLES` and `bonusSchnibbles` are already handled in schnibble units, but the function computes `petterSchnibbles` and `pettedSchnibbles` as `... * 1e18` again. The config comment for `PET_TOTAL_SCHNIBBLES` already assumes 18-decimal scaling, so this extra multiplication inflates every pet payout by another `1e18`.
- Impact: players can generate astronomically large `unfedSchnibbles` balances through petting and then use them to feed NFTs or otherwise break the game economy.

## The global snuggery cap can be bypassed in one purchase
- Location: `src/managers/SnuggeryManager.sol` : `increaseSnuggerySize`
- Mechanism: the function only rejects calls when `previousSize >= MAX_SNUGGERY_SIZE`; it never checks whether `previousSize + _quantity` exceeds the cap. A player just below the limit can therefore buy an arbitrarily large batch of slots in a single call.
- Impact: users can exceed the intended maximum snuggery size, hold more NFTs than allowed, and gain extra chonk, collection bonuses, and reward share.

## Moving a staked munchable leaves its real plot permanently desynchronized
- Location: `src/managers/LandManager.sol` : `transferToUnoccupiedPlot`, `unstakeMunchable`
- Mechanism: `transferToUnoccupiedPlot()` marks the new plot occupied but never updates `toilerState[tokenId].plotId`. Future farming and unstaking still read the old plot id. When the token is later unstaked, the contract clears the old plot instead of the actual occupied one, which can leave the real plot stuck occupied or clear a slot that has since been reused by someone else.
- Impact: attackers can corrupt plot occupancy, create ghost-occupied plots, or invalidate other renters' plot state.

## Renters can keep farming after their plot has become invalid
- Location: `src/managers/LandManager.sol` : `_farmPlots`
- Mechanism: invalid plots are detected with `if (_getNumPlots(landlord) < _toiler.plotId)`, but plot ids are zero-based. If a landlord's plot count drops so a renter now sits on the first invalid plot (`plotId == numPlots`), the condition is false and the token continues accruing as if the plot still exists.
- Impact: renters can continue extracting schnibbles from land that no longer exists after the landlord reduces or removes backing stake.

## The per-account land staking cap is off by one
- Location: `src/managers/LandManager.sol` : `stakeMunchable`
- Mechanism: the limit check is `if (munchablesStaked[mainAccount].length > 10) revert`, so an account with exactly 10 staked munchables can still add an 11th before the condition starts failing.
- Impact: users can exceed the intended staking cap and farm more land rewards than the protocol allows.

