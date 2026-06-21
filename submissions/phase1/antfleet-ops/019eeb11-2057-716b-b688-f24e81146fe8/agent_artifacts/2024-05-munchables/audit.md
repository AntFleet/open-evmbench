# Audit: 2024-05-munchables
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Pet rewards scaled by 1e18 twice
*(consensus, 6 of 6 reports)*
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: `PET_TOTAL_SCHNIBBLES` is already a fully 1e18-scaled quantity (config comment `10e18 / 72`), and `totalSchnibbles` stays in that scale, but the split computes `petterSchnibbles = ((totalSchnibbles * 5) / 11) * 1e18` and `pettedSchnibbles = ((totalSchnibbles * 6) / 11) * 1e18`, applying an extra `1e18` to an already-scaled value (~1e17×–1e18× too large). The integer division also truncates before the multiply.
- Impact: Every eligible pet (10-min petter cooldown, 5-min per petted token) credits ~6e34/~7e34 `unfedSchnibbles` to both parties. Two registered accounts with one petted munchable can mint near-unlimited schnibbles → fed into chonks → dominate per-period point distribution → convert to MUNCH tokens. Effectively unlimited mint of protocol value.

## Migration harvest bonus divides by `(migrateHighestAmount − weightedValue)`, producing an unbounded multiplier
*(consensus, 6 of 6 reports)*
- Location: `src/managers/BonusManager.sol` : `_calculateMigrationBonus` (the `else if (weightedValue >= halfAmount)` branch)
- Mechanism: Bonus is `migrationBonus * (weightedValue - halfAmount) / (migrateHighestAmount - weightedValue)`. The denominator subtracts the attacker-controlled `weightedValue` (= `LockManager.getLockedWeightedValue`) instead of the fixed span `(migrateHighestAmount - halfAmount)`. Since the full-bonus case only catches `weightedValue >= migrateHighestAmount`, this branch runs for `halfAmount <= weightedValue < migrateHighestAmount` and the denominator can be driven toward zero.
- Impact: A migrated user (`didMigrate == true`) inside the window locks an amount placing `weightedValue` just under `migrateHighestAmount`, obtaining an astronomical `_migrationBonus`. `getHarvestBonus → _harvest` applies `dailySchnibbles += dailySchnibbles * bonus / 1e18`, minting essentially unlimited schnibbles → chonks → points → MUNCH. Tuned higher it overflows/reverts `_harvest`/`forceHarvest`, which can also block locks/unlocks.

## WETH yield is claimed against the USDB token (wrong token address)
*(consensus, 6 of 6 reports)*
- Location: `src/managers/RewardsManager.sol` : `_claimYieldForContract` (the WETH branch)
- Mechanism: After `_yieldWETH = IERC20Rebasing(WETH).getClaimableAmount(_contract)`, the code calls `IERC20YieldClaimable(_contract).claimERC20Yield(address(USDB), _yieldWETH)` — passing `address(USDB)` instead of `address(WETH)`. It attempts to claim `_yieldWETH` worth of USDB (already claimed in the prior block) and never claims WETH. `_forwardYield` then sets `ongoingWETH = _yieldWETH`, approves and the distributor `transferFrom`s WETH the manager never received.
- Impact: Any yield run including a WETH-bearing contract either reverts on the USDB over-claim or on the WETH `transferFrom` (manager holds no WETH) — DoS on yield collection — or double-counts/mis-claims USDB. WETH yield is effectively unrecoverable; if the manager already holds stray WETH, that balance can be forwarded under incorrect accounting.

## Period excess accounting underflow permanently bricks `newPeriod`
*(consensus, 4 of 6 reports)*
- Location: `src/managers/ClaimManager.sol` : `newPeriod` (`uint256 _excess = currentPeriod.available - currentPeriod.claimed;`) interacting with `_claimPoints`
- Mechanism: Claims distribute against `availablePoints = currentPeriod.available + _pointsExcess[currentPeriodId]` and accumulate each grant into `currentPeriod.claimed`, so once a prior period leaves `excess > 0`, full participation pushes `claimed` up to `available + excess`. (`getTotalChonk` is read live while `globalTotalChonk` is a snapshot, and post-snapshot registrants further inflate the sum.) The next `newPeriod` then computes `available - claimed` of a larger value from a smaller one and reverts under Solidity 0.8 checked math.
- Impact: `newPeriod` reverts forever; it is the only way to advance periods and reset `claimed`. Because `claimPoints`/`forceClaimPoints` and the `chonkUpdated`/`onlyValidPeriod` modifiers require a live period, this cascades into permanent DoS of claiming, and once `endTime` passes, of `feed`, `importMunchable`, `exportMunchable`. Reachable through ordinary usage.

## `SignatureVerifier.recover` always reverts (`||` instead of `&&`)
*(consensus, 3 of 6 reports)*
- Location: `src/libraries/SignatureVerifier.sol` : `recover` (`if (v != 27 || v != 28) revert InvalidSignature();`)
- Mechanism: The guard is a tautology — for any `v`, at least one of `v != 27`/`v != 28` is true, so the function always reverts before reaching `ecrecover`. The intended check is `&&`. (It also lacks `s`-malleability and `ecrecover == address(0)` checks.)
- Impact: Any code path relying on this verifier is permanently DoS'd. In the supplied sources it is unreferenced (NFT reveal feeds the "signature" bytes into entropy rather than verifying), so currently latent, but it would brick whatever first depends on it.

## ERC20 lock accounting trusts the requested amount and ignores transfer success
*(consensus, 3 of 6 reports)*
- Location: `src/managers/LockManager.sol` : `_lock`, `unlock`
- Mechanism: `_lock` credits `lockedToken.quantity += _quantity` (and computes remainder/NFT entitlement) after `transferFrom` without checking the actual balance delta and without checking the returned boolean; `unlock` likewise ignores `transfer`'s return. Fee-on-transfer, rebasing, or false-returning configured tokens desynchronize recorded locks from escrowed balances.
- Impact: For any active configured non-standard token, a user can be credited for more than the contract received, mint excess reveal entitlement, and potentially drain honest depositors of the same token on unlock or leave the contract insolvent.

## Referral points are minted outside the period emission cap
*(consensus, 2 of 6 reports)*
- Location: `src/managers/ClaimManager.sol` : `_claimPoints` (`_referralBonus = (claimAmount * bonusManager.getReferralBonus())/1e18; _points[player.referrer] += _referralBonus;`)
- Mechanism: The referral bonus credited to `player.referrer` is never added to `currentPeriod.claimed` and is not bounded by `currentPeriod.available` — it is brand-new supply on top of the per-period emission. `register` only blocks `_referrer == msg.sender`.
- Impact: An attacker with two accounts (A refers B) farms uncapped extra points each period whenever B claims, converting them via `convertPointsToTokens` into MUNCH and inflating supply beyond the intended schedule at no cost beyond gas.

## `claimYieldForContracts` has no caller restriction
*(consensus, 2 of 6 reports)*
- Location: `src/managers/RewardsManager.sol` : `claimYieldForContracts`
- Mechanism: Plain `external` with no role check (the original `onlyRole(Role.ClaimYield)` is commented out) and takes a caller-controlled `_contracts[]`. Any address can force Blast yield claims and downstream forwarding, including driving the broken WETH/USDB path into arbitrary supplied addresses.
- Impact: Unprivileged callers control claim timing, can repeatedly trigger the reverting/double-claim yield path, and remove the intended operator gating on treasury cash-flows.
- Reviewer disagreement: One report defends it as a keeper-style function — proceeds route to the configured distributors/treasury, so griefing/availability rather than theft.

## `claimGasFeeForContracts` has no caller restriction
*(consensus, 2 of 6 reports)*
- Location: `src/managers/RewardsManager.sol` : `claimGasFeeForContracts`
- Mechanism: No role restriction; accepts arbitrary target contracts and calls `blastContract.claimMaxGas()` for each, consuming gas-claim state at the caller's chosen time rather than on an authorized operator schedule.
- Impact: Anyone can force premature gas claims for governed contracts, potentially reducing gas yield versus delayed/admin-controlled claiming and disrupting reward operations.
- Reviewer disagreement: One report defends it as a keeper-style function — proceeds route to configured distributors/treasury, not a theft vector.

## `getFeedBonus` truncates `int16`/`uint8` bonuses to `int8`
*(consensus, 2 of 6 reports)*
- Location: `src/managers/BonusManager.sol` : `getFeedBonus` (`int8 realmBonus = int8(realmBonuses[realmIndex]);` and `int16(int8(rarityBonus))`)
- Mechanism: `realmBonuses` is `int16[]` but each element is downcast to `int8`, and `rarityBonus` (a `uint8`) is reinterpreted via `int8`. Any realm value outside `[-128,127]` or rarity `>127` wraps (e.g. `200 → -56`), then drives `finalBonus = 1e16 * sumBonuses` and the `[-20e16,100e16]` clamp locks in the wrong sign.
- Impact: Config values legal for the storage type but exceeding `int8` range produce feed bonuses with wrong magnitude/sign (a positive config can become a penalty), silently corrupting chonk/feed accounting.
- Reviewer disagreement: One report defends it as admin-config-controlled and clamped to `[-20e16,100e16]`, i.e. a latent truncation rather than attacker-triggerable.

## Snuggeries over 10 NFTs break harvest bonus (capped array vs full size loop)
*(consensus, 2 of 6 reports)*
- Location: `src/managers/SnuggeryManager.sol` : `getSnuggery`; `src/managers/BonusManager.sol` : `_calculateLevelBonus`
- Mechanism: `getSnuggery` returns an array capped at 10 entries but also returns the full `_snuggerySize`. `_calculateLevelBonus` loops to `_snuggerySize` and indexes the capped array, causing an out-of-bounds revert once a player imports more than 10 NFTs (the slot-expansion flow is supported via `increaseSnuggerySize`).
- Impact: Accounts with >10 imported NFTs can have harvest bonus calculation revert, blocking `harvest()` and any path that `forceHarvest`s first — including lock/unlock and snuggery updates — potentially preventing withdrawal of locked tokens until the snuggery is reduced.

## Munchadex changes are harvested retroactively
*(consensus, 2 of 6 reports)*
- Location: `src/managers/MunchadexManager.sol` : `updateMunchadex`
- Mechanism: The function mutates the sender/receiver Munchadex counters before calling `accountManager.forceHarvest`, so harvest-bonus calculation reads the post-transfer Munchadex state and applies it to the entire elapsed period since the user's last harvest, even though the NFT was only just received/minted.
- Impact: A user can let an account accrue unharvested time, then receive/mint a unique NFT that completes a bonus threshold and obtain the higher Munchadex bonus retroactively for prior accrual time.

## Minority findings

## `getTotalChonk` uses a `uint8` loop counter and reverts at ≥256 munchables
*(minority, 1 of 6 reports)*
- Location: `src/managers/SnuggeryManager.sol` : `getTotalChonk` (`for (uint8 i; i < snuggery.length; i++)`)
- Mechanism: The loop index is `uint8` while `snuggery.length` is `uint256`; `maxSnuggerySize` is a `uint16` raisable via `increaseSnuggerySize`. At length 256, `i++` at `i == 255` overflows and reverts.
- Impact: A player filling ≥256 slots makes `getTotalChonk(self)` always revert; since `_claimPoints`/`chonkUpdated` call it, that player can no longer claim, feed, import or export — a self-inflicted permanent lock-out.

## Early unlock by reducing duration near expiry
*(minority, 1 of 6 reports)*
- Location: `src/managers/LockManager.sol` : `setLockDuration`
- Mechanism: The reduction check compares `block.timestamp + _duration` against existing `unlockTime`, but the stored value is then set to `lastLockTime + _duration`. After enough time elapses, a small `_duration` passes the check while making the new `unlockTime` land in the past.
- Impact: A locker can withdraw before the originally committed end. E.g. with a 365-day lock, at day 364 set duration to 1 day; the check passes but `unlockTime` becomes day 1.

## Migration can burn NFTs without checking current ownership
*(minority, 1 of 6 reports)* *(conflicting reviews: 1 of 6 reports defended this code path)*
- Location: `src/managers/MigrationManager.sol` : `burnNFTs`, `burnRemainingPurchasedNFTs`, `migrateAllNFTs`, `migratePurchasedNFTs`, `_migrateNFTs`
- Mechanism: Migration uses snapshot ownership keyed by `(_user, tokenId)` and calls `_oldNFTContract.burn(tokenId)` without checking current `ownerOf(tokenId)`; the replacement NFT/points are credited to the snapshot user, not the current owner.
- Impact: If old NFTs remain transferable after the snapshot, a snapshot owner can sell/transfer an old NFT then migrate/burn it, destroying the buyer's NFT while receiving the new NFT or points.
- Reviewer disagreement: Another report defends the path — the `claimed` flags and `UserLockedChoice` guards prevent double-mint/double-burn and effects accrue to the targeted `_user`.

## Upgradeable proxies are takeover-prone if not initialized atomically
*(minority, 1 of 6 reports)*
- Location: `src/config/BaseConfigStorageUpgradeable.sol` : `initialize`; `src/managers/AccountManager.sol` : `initialize`; `src/managers/ClaimManager.sol` : `initialize`
- Mechanism: The public initializer lets the first caller set `configStorage`; `_authorizeUpgrade` later trusts `configStorage.getUniversalRole(Role.Admin)`, so an attacker-controlled config storage makes the attacker the upgrade admin.
- Impact: If any proxy is deployed without initializer calldata in the proxy constructor, an attacker can front-run initialization, set malicious config storage, and gain control over upgrades and role-gated behavior for that proxy.

## Zero-amount `lockOnBehalf` can perpetually relock victim funds
*(minority, 1 of 6 reports)*
- Location: `src/managers/LockManager.sol` : `lockOnBehalf`, `_lock`
- Mechanism: `lockOnBehalf` lets any caller choose `_onBehalfOf`, and `_lock` accepts `_quantity == 0`, yet still rewrites `lockedToken.lastLockTime` and `lockedToken.unlockTime` for the recipient's existing lock.
- Impact: An attacker can call `lockOnBehalf(token, 0, victim)` at no cost and repeatedly extend a victim's unlock time, indefinitely grief-locking their position (precondition: victim has an existing lock for an active configured token).

## Unlocked remainders can be reused to mint under-collateralized reveals
*(minority, 1 of 6 reports)*
- Location: `src/managers/LockManager.sol` : `_lock`, `unlock`
- Mechanism: `_lock` carries `lockedToken.remainder` forward when computing new NFT entitlement, but `unlock` never clears or recomputes that remainder when the underlying quantity is withdrawn.
- Impact: A user can lock just below `nftCost`, wait until unlock, withdraw, then lock only the missing dust during a later lockdrop and receive an NFT reveal while only the dust is actually locked.

## Mixed-token migration snapshots collapse into a single token debt
*(minority, 1 of 6 reports)*
- Location: `src/managers/MigrationManager.sol` : `loadMigrationSnapshot`, `lockFundsForAllMigration`, `_migrateNFTs`
- Mechanism: `loadMigrationSnapshot` sums all locked migration amounts into `totalLockedAmount` but overwrites `tokenLocked` with each row's token, so payment/locking treats the whole aggregate as denominated in only the last token seen.
- Impact: A user with legacy locks across multiple token types can underpay or lock the wrong asset for migration if the final stored token is cheaper or differently scaled.

## Primordial claim ignores the empty-snuggery eligibility rule
*(minority, 1 of 6 reports)*
- Location: `src/managers/PrimordialManager.sol` : `claimPrimordial`
- Mechanism: The interface says primordial claiming requires an empty snuggery, but `claimPrimordial` only checks registration, global enablement, and whether the caller already claimed.
- Impact: Any registered player can claim a primordial even after already owning/using munchables, then feed and hatch it into an additional NFT (precondition: `PrimordialsEnabled`).

## Unchecked ERC20 transfer return in distributor and migration paths
*(minority, 1 of 6 reports)*
- Location: `src/distributors/FundTreasuryDistributor.sol` : `receiveTokens`; `src/managers/MigrationManager.sol` : `lockFundsForAllMigration`
- Mechanism: These call `transfer`/`transferFrom` through `IERC20` and ignore the returned boolean; tokens that return `false` instead of reverting are treated as successful. (Reported alongside the LockManager consensus finding but extending to these additional contracts.)
- Impact: For a configured false-return token, attackers can receive migration state or distribution success without tokens moving, mutating accounting without moving funds.

## Oracle that disapproved can later approve without clearing its disapproval
*(minority, 1 of 6 reports)*
- Location: `src/managers/LockManager.sol` (USD price proposal flow) : `proposeUSDPrice` / `approve` / `disapprove`
- Mechanism: A price-feed oracle that previously disapproved a proposal can subsequently approve it without its prior disapproval being cleared — a governance state inconsistency in the proposal approval bookkeeping.
- Impact: Skews the approve/disapprove tally for a USD-price proposal. The finding report itself downgraded this as requiring trusted `PriceFeed_*` roles and not independently exploitable.

## `getSnuggery` out-of-bounds write for nonzero `_start`
*(minority, 1 of 6 reports)*
- Location: `src/managers/SnuggeryManager.sol` : `getSnuggery`
- Mechanism: For a nonzero `_start` argument, the indexing produces an out-of-bounds write into the returned array.
- Impact: Corrupted/reverting reads for nonzero `_start`. The finding report itself downgraded this as view-only and noted all current callers pass `0`.

---

**Reconciliation check:** Distinct findings across all six input reports (by code path + root cause), including two items surfaced in reports' "checked/notes" sections: **23**. Findings emitted above: **23** (12 consensus + 11 minority). No findings dropped; consensus items reported by 4+ reports (pet 1e18, migration bonus, WETH/USDB, period underflow) have no defending report, while several 2-of-6 items (claim-entrypoint access control, `getFeedBonus` truncation) and the migration-burn minority finding carry explicit defenses from other reports, preserved as disagreement rather than resolved.

