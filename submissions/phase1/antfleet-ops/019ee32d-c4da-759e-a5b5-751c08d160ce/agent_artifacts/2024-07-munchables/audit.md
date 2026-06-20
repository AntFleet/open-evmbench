# Audit: 2024-07-munchables

Here is the security audit of the provided smart contracts.

## 1. Permanent NFT Freeze via Underflow in LandManager during USD Price Updates
- Location: `LandManager.sol` : `_farmPlots` (via `unstakeMunchable`, `farmPlots`, and `transferToUnoccupiedPlot`)
- Mechanism: When a USD price update occurs in the `LockManager`, it updates the `usdPrice` attribute but does not trigger `updatePlotMetadata` on the `LandManager`. Consequently, a landlord's plot count instantly decreases. If a renter's staked Munchable resides on a plot ID higher than the newly reduced plot count, `_farmPlots` will attempt to use the landlord's outdated `lastUpdated` timestamp (which is older than the renter's stake date). Estimating the accumulated schnibbles dynamically triggers `timestamp - _toiler.lastToilDate`. Since `timestamp` (the older `lastUpdated` time) is smaller than `_toiler.lastToilDate` (the renter's stake date), the subtraction underflows, causing the transaction to revert.
- Impact: Renter accounts will have their staked Munchable NFTs permanently locked inside the `LandManager` contract because `unstakeMunchable` and `transferToUnoccupiedPlot` rely on the `forceFarmPlots` modifier which executes `_farmPlots` and invariably reverts on the underflow.

## 2. Math and Accounting Error in LandManager Reward Calculation
- Location: `LandManager.sol` : `_farmPlots`
- Mechanism: The contract calculates the total rewards using the formula: `schnibblesTotal = uint256((int256(schnibblesTotal) + (int256(schnibblesTotal) * finalBonus)) / 100);`. Mathematically, this divides the entire base amount plus the bonus by 100, instead of dividing only the bonus part of the calculation. For example, if a player has a 0% bonus (`finalBonus = 0`), they only receive 1% of their earned base rewards. If they have a 15% bonus (`finalBonus = 15`), they receive only 16% of their base rate.
- Impact: Massive loss of rewards and skewed reward distribution for both renters and landlords.

## 3. Zero-Chonk Claim Lockout in ClaimManager
- Location: `ClaimManager.sol` : `_claimPoints` (via `claimPoints`, `forceClaimPoints`)
- Mechanism: In `_claimPoints`, the player's `_lastClaimPeriod[_player]` tracking variable is updated to `currentPeriod.id` regardless of whether the calculated `claimAmount` is greater than zero. If a newly registered user locks a token or imports a Munchable before they have configured Snuggery chonks, the action will trigger `_claimPoints` while their claimable amount is still 0. This instantly locks their `_lastClaimPeriod` to the current period ID.
- Impact: If the player afterwards acquires/stakes a Munchable and accumulates positive chonks in that same period, they will be utterly unable to claim their points for the rest of that period because the entry condition `_lastClaimPeriod[_player] < currentPeriodId` evaluates to false.

## 4. Wiped Fractions and Loss of Progress in LockManager Unlocks
- Location: `LockManager.sol` : `unlock`
- Mechanism: The contract uses the `remainder` variable to track fractional locked amounts that did not meet the full cost of an NFT, allowing users to build up to their next NFT over multiple deposits. However, inside `unlock()`, the statement `lockedToken.remainder = 0;` is executed. If a user unlocks even a portion of their locked tokens, their fractional remainder balance is completely wiped out.
- Impact: Wipes out the progress of players towards their next NFT, forcing them to lose accrued fractional assets.

## 5. Token Mismatch and Overwriting during Migration Snapshot Load
- Location: `MigrationManager.sol` : `loadMigrationSnapshot`
- Mechanism: When migrating a user's locked snapshots from the old contract, the loop overwrites `_userLockedAmounts[_user].tokenLocked = data[i].token;` with the latest record while summing the quantities of *all* records into `totalLockedAmount`. If a user had multiple different tokens locked (e.g., USDB and WETH), the contract overwrites the token address with only one of them.
- Impact: The user is forced to deposit the aggregate sum of all their distinct locked tokens in the denomination of whichever single token was processed last in the snapshot array, leading to failed migrations or loss of funds.

## 6. Referral Point Misattribution and Lockout on Sub-accounts
- Location: `ClaimManager.sol` : `_claimPoints`
- Mechanism: When assigning referral bonuses, `_claimPoints` directly increases `_points[player.referrer] += _referralBonus;` without translating the referral address to its main account if it is a sub-account. However, the `getPoints` getter fetches points from `accountManager.getMainAccount(_player)`.
- Impact: If a sub-account is specified as the referrer, the referral points are credited to `_points[subAccount]` but become inaccessible and invisible since the UI displays `_points[mainAccount]`.
