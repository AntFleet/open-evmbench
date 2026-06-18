# Audit: 2024-07-munchables

## Consensus findings

## Pet rewards double‑scaled by 1e18
*(consensus)*
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: `PET_TOTAL_SCHNIBBLES` is already configured as an 18‑decimal amount (in‑code comment `// 10e18 / 72` ≈ `1.39e17`), but `pet()` computes each side’s share as `((totalSchnibbles * share) / 11) * 1e18`, applying a *second* `1e18` scaling before crediting `unfedSchnibbles`:
  ```solidity
  uint256 bonusSchnibbles   = (PET_TOTAL_SCHNIBBLES * bonusPercent) / 1e18;
  uint256 totalSchnibbles   = PET_TOTAL_SCHNIBBLES + bonusSchnibbles;
  uint256 petterSchnibbles  = ((totalSchnibbles * 5) / 11) * 1e18;
  uint256 pettedSchnibbles  = ((totalSchnibbles * 6) / 11) * 1e18;
  ```
  Because the `/11` happens on the already‑large number before the `*1e18`, the result is scaled ~1e18× beyond intent, and the locked‑token pet bonus is additionally truncated away by the integer division.
- Impact: Petting is permissionless (only 10‑min petter / 5‑min per‑token cooldowns). Any registered user can pet another user’s munchable and mint roughly `1e18`× the intended schnibbles every cooldown cycle, flowing into chonks → claim points → MUNCH mint. Preconditions: two registered accounts and a petted munchable in the target snuggery.

## Snuggery size cap can be exceeded in one call
*(consensus)*
- Location: `src/managers/SnuggeryManager.sol` : `increaseSnuggerySize`
- Mechanism: The only cap check is on the *previous* size; the resulting size is never bounded:
  ```solidity
  if (previousSize >= MAX_SNUGGERY_SIZE) revert SnuggeryMaxSizeError();
  _player.maxSnuggerySize += uint16(_quantity);   // previousSize + _quantity never checked
  ```
  `_quantity` is an unbounded `uint8` (up to 255), so while `previousSize` is one below the cap (e.g. 11 with cap 12), a single call with `_quantity = 255` raises `maxSnuggerySize` to 266.
- Impact: A player with enough points bypasses the intended snuggery‑size cap, allowing them to import far more chonk‑bearing munchables (`importMunchable` gates on `length >= maxSnuggerySize`), inflating their share of every claim period and triggering the “full snuggery” harvest bonus.

## Signed→unsigned underflow in plot farming mints near‑infinite schnibbles
*(consensus)*
- Location: `src/managers/LandManager.sol` : `_farmPlots` (the `finalBonus` / `schnibblesTotal` computation)
- Mechanism: `finalBonus` is the sum of a (possibly negative) realm bonus and a rarity bonus, used with no clamping:
  ```solidity
  finalBonus = int16(REALM_BONUSES[realm*5 + landlordRealm]) + int16(int8(RARITY_BONUSES[rarity]));
  schnibblesTotal = (timestamp - _toiler.lastToilDate) * BASE_SCHNIBBLE_RATE;
  schnibblesTotal = uint256((int256(schnibblesTotal) + (int256(schnibblesTotal) * finalBonus)) / 100);
  ```
  This is `schnibblesTotal * (1 + finalBonus) / 100`. `REALM_BONUSES` legitimately contains negative penalties; `BonusManager.getFeedBonus` clamps the analogous result to `[-20e16, 100e16]`, but `LandManager` does **not**. Whenever `finalBonus <= -2`, the product is negative and `uint256(negativeInt256)` wraps to a value near `2**256`, then credited via `renterMetadata.unfedSchnibbles += (schnibblesTotal - schnibblesLandlord)`.
- Impact: A renter picks a landlord whose `snuggeryRealm` yields a net‑negative bonus for the renter’s munchable realm/rarity, stakes, lets one block elapse, and calls `farmPlots()` — instead of a penalty they (and the landlord) receive astronomically large `unfedSchnibbles`. Permissionless, unbounded inflation of the entire reward economy; can also strike honest users by accident, corrupting global accounting. Preconditions: configured negative realm bonuses and a staked munchable whose bonus path makes the signed result negative.

## Additional findings (single-reviewer)

## `transferToUnoccupiedPlot` never clears the `dirty` flag
*(Reviewer A only)*
- Location: `src/managers/LandManager.sol` : `transferToUnoccupiedPlot` (and `dirty` handling in `_farmPlots`)
- Mechanism: In `_farmPlots`, when a landlord shrinks their plots a toiler is marked `toilerState[tokenId].dirty = true`, after which `if (_toiler.dirty) continue;` skips it permanently. The intended remedy `transferToUnoccupiedPlot` updates `latestTaxRate` and moves the plot but **never sets `dirty = false`**; only `stakeMunchable`/`unstakeMunchable` reset `dirty`.
- Impact: A renter who follows the documented “move to an unoccupied plot” recovery path stays permanently `dirty`; `farmPlots()` keeps `continue`‑ing the munchable, so it earns zero schnibbles forever until fully unstaked (losing accrued time).

## `transferToUnoccupiedPlot` leaves stale occupancy / `plotId` records
*(Reviewer B only)*
- Location: `src/managers/LandManager.sol` : `transferToUnoccupiedPlot`
- Mechanism: The function marks the old plot unoccupied and the new plot occupied, but never updates `toilerState[tokenId].plotId` to the new `plotId`. Future calls still treat the original plot as the token’s location.
- Impact: A renter can repeatedly move one staked NFT into different plots and leave each new plot permanently marked occupied, blocking a landlord’s available plots and corrupting later unstake/farming behavior. Preconditions: attacker has one staked munchable and there are unoccupied plots to target.

*(Note: Reviewers A and B both flag incomplete state updates in `transferToUnoccupiedPlot`, but identify distinct missing writes — the `dirty` flag vs. `plotId` — so they are preserved as separate findings.)*

## Off‑by‑one in plot‑validity check (`<` instead of `<=`)
*(Reviewer A only)*
- Location: `src/managers/LandManager.sol` : `_farmPlots` — `if (_getNumPlots(landlord) < _toiler.plotId)`
- Mechanism: Plots are 0‑indexed, so for `N` plots valid ids are `0..N-1`. The dirty/timestamp‑freeze guard fires only when `numPlots < plotId`, missing the boundary `numPlots == plotId` (already out of range). The same off‑by‑one is mirrored inconsistently by the `plotId >= totalPlotsAvail` checks in `stakeMunchable`/`transferToUnoccupiedPlot`.
- Impact: A renter occupying the exact boundary plot keeps accruing schnibbles at full `block.timestamp` against a plot the landlord no longer backs, over‑accruing relative to intended accounting.

## Referral bonus minted as over‑emission beyond the period budget
*(Reviewer A only)*
- Location: `src/managers/ClaimManager.sol` : `_claimPoints`
- Mechanism:
  ```solidity
  _referralBonus = (claimAmount * bonusManager.getReferralBonus()) / 1e18;
  _points[player.referrer] += _referralBonus;
  _points[_player] += claimAmount;
  currentPeriod.claimed += claimAmount;   // referral bonus NOT counted
  ```
  The referrer’s bonus is minted but never added to `currentPeriod.claimed` nor checked against `available`. `register` only blocks `_referrer == msg.sender`, so a user can set a second wallet they control as referrer. (A `// TODO` in the code acknowledges emission can exceed the budget.)
- Impact: Unbounded points inflation beyond the configured per‑period emission, self‑dealable via a controlled referrer address.

## NFT blacklist only checks the sender side
*(Reviewer A only)*
- Location: `src/tokens/MunchNFT.sol` : `_update`
- Mechanism: `if (_blacklistAccount[from] || _blacklistToken[_tokenId]) revert ForbiddenTransferError();` — only `from` is checked, never `_to`. A blacklisted account can still be the recipient of transfers/mints.
- Impact: A blacklisted address can keep acquiring munchables (received via transfer), partially defeating the blacklist control.

## Munchadex bonus applied retroactively on transfers
*(Reviewer B only)*
- Location: `src/managers/MunchadexManager.sol` : `updateMunchadex`
- Mechanism: On NFT transfers, the Munchadex counters are updated before `accountManager.forceHarvest()` is called. The recipient is harvested *after* receiving the new Munchadex state, so their entire unharvested interval is calculated as if they already held the transferred NFT.
- Impact: A player can wait with locked value and an old `lastHarvestDate`, receive NFTs that improve their Munchadex bonus, and get the higher bonus applied retroactively to past time — inflating schnibble rewards beyond what was earned while actually holding the NFTs.

## Production‑shipped mock managers expose unguarded state mutators
*(Reviewer A only)*
- Location: `src/mock/MockAccountManager.sol` (`giveSchnibbles`), `src/mock/MockClaimManager.sol` (`givePoints`), `src/mock/MockLockManager.sol` (`setLockedTokenForTest`, `callAddRevealForTest`), `src/mock/MockSnuggeryManager.sol` (`setGlobalTotalChonk`, `spendPoints`), `src/mock/MockMunchadexManager.sol`, etc.
- Mechanism: These contracts subclass the real managers and add fully public, unauthenticated functions that mint schnibbles/points, set arbitrary locked balances, and overwrite global accounting. They share the exact role/config plumbing of the real contracts.
- Impact: If any mock is wired into `ConfigStorage` on a live deployment, anyone can mint unlimited schnibbles/points and forge locked balances. Should be confirmed test‑only and excluded from production configuration.

