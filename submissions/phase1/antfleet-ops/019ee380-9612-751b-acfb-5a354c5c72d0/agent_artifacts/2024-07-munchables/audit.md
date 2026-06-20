# Audit: 2024-07-munchables

I audited the Munchables contract set. Below are the genuine security issues I found, ordered roughly by severity.

## Stale plot pointer in `transferToUnoccupiedPlot` permanently locks plots / corrupts occupancy
- Location: `src/managers/LandManager.sol` : `transferToUnoccupiedPlot`
- Mechanism: The function frees the old plot and marks the new plot occupied, but it never updates `toilerState[tokenId].plotId` to `plotId`. After the move, `toilerState[tokenId].plotId` still references `oldPlotId`. Consequently, when the user later calls `unstakeMunchable`, the cleanup `plotOccupied[_toiler.landlord][_toiler.plotId] = Plot({occupied:false, tokenId:0})` clears the *old* plot (already free), while the *new* plot (`plotId`) is left flagged `occupied` forever with no toiler referencing it. The function also never resets `dirty` or refreshes `lastToilDate` for the moved token.
- Impact: A renter can permanently occupy/brick a landlord's plot (`occupied == true` with a non-existent toiler), a denial-of-service on plots that can be repeated to lock out all of a landlord's plots. The double-free of `oldPlotId` also lets two munchables believe they hold the same plot, corrupting plot accounting.

## `_farmPlots` off-by-one lets out-of-range plots keep farming
- Location: `src/managers/LandManager.sol` : `_farmPlots`
- Mechanism: Validity is checked with `if (_getNumPlots(landlord) < _toiler.plotId)`. `plotId` is a 0-based index and `_getNumPlots` returns a count, so valid indices are `0 .. numPlots-1`. When `numPlots == plotId` the plot is actually out of range, but `numPlots < plotId` is false, so the token is not marked `dirty` and continues to accrue schnibbles against the live `block.timestamp`. The comparison should be `<=`.
- Impact: When a landlord reduces their locked value (shrinking plot count), a munchable sitting on the now-invalid boundary plot keeps farming full schnibbles instead of being frozen at `plotMetadata.lastUpdated`, inflating rewards beyond what the landlord's stake supports.

## Pet rewards are over-scaled by ~1e18 (massive schnibble inflation)
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: `PET_TOTAL_SCHNIBBLES` is already an 1e18-scaled value (config comment `10e18 / 72`). The payout math multiplies the already-scaled total by `1e18` again: `petterSchnibbles = ((totalSchnibbles * 5) / 11) * 1e18;` (and likewise for `pettedSchnibbles`). This applies the 1e18 scaling twice.
- Impact: Each `pet()` credits ~1e18× more `unfedSchnibbles` than intended (on the order of 1e34 vs. the ~1e18 scale used everywhere else, e.g. harvest produces ~1e20/day for a $1000 lock). Any registered player can repeatedly pet to mint effectively unlimited schnibbles, which convert into chonks → claim points → MUNCH tokens, draining the points/token economy.

## Permissionless yield and gas claiming in RewardsManager
- Location: `src/managers/RewardsManager.sol` : `claimYieldForContracts`, `claimGasFeeForContracts`
- Mechanism: The active implementations have no access control (the prior `onlyRole(Role.ClaimYield)` variants are commented out). `claimGasFeeForContracts` calls `blastContract.claimMaxGas(...)` for arbitrary caller-supplied contract addresses and then `gasFeeDistributor.receiveTokens{value:_gas}(...)`; `claimYieldForContracts` similarly drives `_claimYieldForContract` for arbitrary addresses, which calls back into each target's `claimERC20Yield`.
- Impact: Anyone can force-claim gas/yield for any managed contract at any time. At minimum this is a griefing/forced-accounting vector (claims are pushed to the configured distributors on the attacker's schedule, and gas claiming consumes the accrued gas-seconds prematurely). If `gasFeeDistributor` is unset it reverts; the broader concern is that a privileged economic operation is callable by untrusted accounts.

## Unclamped negative bonus can underflow to a huge reward in `_farmPlots`
- Location: `src/managers/LandManager.sol` : `_farmPlots`
- Mechanism: `finalBonus` is computed as `realmBonus + rarityBonus` and applied with `schnibblesTotal = uint256((int256(schnibblesTotal) + (int256(schnibblesTotal) * finalBonus)) / 100)`. Unlike `BonusManager.getFeedBonus`, which clamps the combined bonus to `[-20, 100]`, this code path applies the raw config values with no bounds. If the realm/rarity config yields `finalBonus <= -101`, the inner expression goes negative and the `uint256(...)` cast wraps to an enormous positive value.
- Impact: With adversarial or mis-set bonus config, a renter receives a near-infinite schnibble payout for a single farm. Even absent malice, the divergence from the clamped logic in `BonusManager` is an inconsistency that removes the safety bound present elsewhere.

## `MigrationManager.rescue` ERC20 path is broken (uses `transferFrom` from self)
- Location: `src/managers/MigrationManager.sol` : `rescue`
- Mechanism: For non-ETH tokens it calls `IERC20(_tokenContract).transferFrom(address(this), _returnAddress, _quantity)`. Standard ERC20s require an allowance for the `from` account even when `from == msg.sender`/`address(this)`; the contract has no self-allowance, so this reverts.
- Impact: The admin rescue path for stuck ERC20 tokens (USDB/WETH and any other) does not work, so funds accidentally sent to the contract cannot be recovered via the intended mechanism. (Should use `transfer`.)

## Off-by-one in staked-munchable limit
- Location: `src/managers/LandManager.sol` : `stakeMunchable`
- Mechanism: The cap is enforced with `if (munchablesStaked[mainAccount].length > 10) revert TooManyStakedMunchiesError();`. Since the check happens before the push, a user with exactly 10 staked passes (10 is not `> 10`) and stakes an 11th.
- Impact: The intended maximum (10) can be exceeded by one. Low severity, but it widens the unbounded-iteration surface of `_farmPlots`/`_removeTokenIdFromStakedList`.

---

Notes on things I examined and deliberately did **not** flag as vulnerabilities: the intentional reuse of unrelated `StorageKey` slots in `LandManager._reconfigure`/`AccountManager._reconfigure` (deployment-config aliasing, not a code flaw); the unbounded referral-point inflation in `ClaimManager._claimPoints` (explicitly acknowledged by the in-code TODO); and the `unlock` path not reducing previously granted NFT reveals (intended design). `MunchToken`/`OldMunchNFTTest` are flagged in-source as not-for-audit/test scaffolding.

