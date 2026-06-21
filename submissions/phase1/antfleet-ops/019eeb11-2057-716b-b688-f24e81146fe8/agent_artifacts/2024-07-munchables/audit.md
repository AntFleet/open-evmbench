# Audit: 2024-07-munchables
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Pet rewards are scaled by 1e18 twice
*(consensus, 6 of 6 reports)*
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: `PET_TOTAL_SCHNIBBLES` is already a 1e18-scaled config value (documented in `_reconfigure` as `10e18 / 72 ≈ 1.39e17`). The split `(totalSchnibbles * 5)/11` and `(totalSchnibbles * 6)/11` already partitions `totalSchnibbles`, but each share is then multiplied by `1e18` a second time (`... * 1e18`), so each pet pays ≈`6.3e34`/`7.5e34` schnibbles instead of the intended ~5/~6. (Shot 3 notes the units bug is two-sided: if instead set to the bare integer the `*1e18` implies, the `bonusSchnibbles` term rounds to 0.)
- Impact: Any registered account can `pet` another player's munchable (subject only to the 10-minute petter / 5-minute per-token cooldowns) and mint astronomically inflated `unfedSchnibbles` to both petter and petted. These feed NFT chonks → period points (`ClaimManager._claimPoints`) → minted MUNCH, dominating the entire emission economy.
- Reviewer disagreement: none.

## Negative realm/rarity bonus causes signed→unsigned wrap, minting ~2²⁵⁶ schnibbles
*(consensus, 5 of 6 reports)*
- Location: `src/managers/LandManager.sol` : `_farmPlots` (the `finalBonus` / `schnibblesTotal` block)
- Mechanism: `finalBonus = REALM_BONUSES[...] + RARITY_BONUSES[...]` is used raw with **no clamp**, in `schnibblesTotal = uint256((int256(schnibblesTotal) + (int256(schnibblesTotal) * finalBonus)) / 100)` — i.e. `S*(1 + finalBonus)/100`. The same config tables are clamped to ≥`-20` (i.e. negative) by `BonusManager.getFeedBonus`, confirming negative sums are expected. For any `finalBonus <= -2`, the numerator is negative and the `uint256(...)` cast wraps to ~`2²⁵⁶`. (Several reports also note the formula is wrong even for positive bonuses, under-crediting to ~S/100.)
- Impact: A renter (using a second account as landlord to bypass `CantStakeToSelfError`, with uninitialized/zero tax to avoid the tax-multiply overflow) stakes a realm-mismatched munchable, waits a block, and calls `farmPlots`. `renterMetadata.unfedSchnibbles` is credited ~`2²⁵⁶`, convertible to chonks → points → near-unlimited MUNCH. Full economic drain.
- Reviewer disagreement: gpt-5.5 shot 1 read this same cast as *reverting* (DoS/brick) rather than wrapping — see the corresponding minority entry below.

## `increaseSnuggerySize` can exceed `MAX_SNUGGERY_SIZE`
*(consensus, 5 of 6 reports)*
- Location: `src/managers/SnuggeryManager.sol` : `increaseSnuggerySize`
- Mechanism: The only cap check is `if (previousSize >= MAX_SNUGGERY_SIZE) revert SnuggeryMaxSizeError();`, then `_player.maxSnuggerySize += uint16(_quantity)`. It never checks `previousSize + _quantity <= MAX_SNUGGERY_SIZE`, so from any size below the cap a single large `_quantity` (up to 255) sets `maxSnuggerySize` arbitrarily high (e.g. 6 + 255 = 261 vs cap 12).
- Impact: A player willing to spend points can grow their snuggery far beyond the design limit (`importMunchable` gates only on `maxSnuggerySize`), holding far more NFTs, accumulating more chonk, and taking a disproportionate share of period point emissions. Breaks the protocol-wide snuggery-size invariant.
- Reviewer disagreement: none.

## Permissionless yield / gas claiming on arbitrary contracts
*(consensus, 2 of 6 reports)* *(conflicting reviews: 1 of 6 reports defended this code path)*
- Location: `src/managers/RewardsManager.sol` : `claimYieldForContracts`, `claimGasFeeForContracts`
- Mechanism: Both functions are `external` with no access control; the previous `claimYield`/`claimGasFee` variants (now commented out) were `onlyRole(Role.ClaimYield)`. Anyone can pass an arbitrary contract list and force `blastContract.claimAllYield(...)` / `claimMaxGas(...)` and the ERC-20 yield-claim path. (Shot 1 also notes the omitted zero-address distributor/config checks.)
- Impact: Proceeds route to the configured distributor → Treasury (no direct theft), but it is an unauthorized, externally-reachable state-changing action: forcing premature/ill-timed gas and yield claims for any managed contract, and draining accrued gas refunds on demand. If `gasFeeDistributor` is unset, claimed ETH may be forwarded to address zero.
- Reviewer disagreement: opus shot 1 defended this as not exploitable — proceeds are forwarded only to the configured distributor → Treasury, so there is no attacker-controllable sink.

## Off-by-one invalid-plot check lets removed plots keep farming
*(consensus, 2 of 6 reports)*
- Location: `src/managers/LandManager.sol` : `_farmPlots`
- Mechanism: The invalid-plot check is `_getNumPlots(landlord) < _toiler.plotId`, but valid plot IDs are `0..numPlots-1`. When the landlord's plot count shrinks to exactly `plotId` (e.g. drops to 0 with `plotId == 0`, since `0 < 0` is false), the now-invalid plot is still treated as valid and is not marked dirty.
- Impact: A colluding/renting account stakes into a high-index plot, the landlord then unlocks enough value to remove that plot, and the renter keeps accruing farming rewards from land that no longer exists.
- Reviewer disagreement: none. (Note: opus shot 1 flags a *different* bug in the same branch — see the timestamp-underflow minority entry.)

## Uninitialized landlord metadata gives renters zero-tax plots
*(consensus, 2 of 6 reports)*
- Location: `src/managers/LandManager.sol` : `stakeMunchable`
- Mechanism: `stakeMunchable` does not require or initialize `plotMetadata[landlord]` (no `lastUpdated != 0` check). If `currentTaxRate`/`lastUpdated` are still zero, the renter's recorded `latestTaxRate` is the default zero instead of `DEFAULT_TAX_RATE`.
- Impact: A renter can stake to an eligible landlord with plots but uninitialized metadata and farm at 0% tax until metadata is initialized and the toiler state refreshes, depriving the landlord/protocol of the intended tax split.
- Reviewer disagreement: none.

## `transferToUnoccupiedPlot` never updates the toiler's `plotId`, corrupting plot occupancy
*(consensus, 2 of 6 reports)*
- Location: `src/managers/LandManager.sol` : `transferToUnoccupiedPlot`
- Mechanism: The function frees `plotOccupied[landlord][oldPlotId]`, marks the new `plotId` occupied, and updates `latestTaxRate`, but never writes `toilerState[tokenId].plotId = plotId`. The toiler keeps pointing at the old plot (the emitted event even reports the stale id).
- Impact: On `unstakeMunchable` the code frees the *old* (already-free) plot and leaves the *new* plot permanently occupied with no token to release it, shrinking the landlord's usable plots forever; a follow-on stake into the freed old plot enables double-occupancy and permanent plot griefing/locking. Reachable by any registered user with a staked munchable.
- Reviewer disagreement: none.

## Staked-munchable cap off-by-one allows one extra NFT
*(consensus, 2 of 6 reports)*
- Location: `src/managers/LandManager.sol` : `stakeMunchable`
- Mechanism: The cap check is `if (munchablesStaked[mainAccount].length > 10)`, so an account with exactly 10 staked NFTs can stake an 11th before the condition triggers.
- Impact: Any player with enough NFTs and available plots can exceed the intended staking cap by one, increasing farming output beyond the designed maximum.
- Reviewer disagreement: none.

## Minority findings

## `configureToken` accepts `decimals > 18` and bricks all weighted-value reads
*(minority, 1 of 6 reports)*
- Location: `src/managers/LockManager.sol` : `configureToken` / `getLockedWeightedValue`
- Mechanism: `configureToken` only validates `nftCost != 0`, with no bound on `_tokenData.decimals`. For any active token configured with `decimals > 18`, `getLockedWeightedValue` evaluates `10 ** (18 - decimals)`, where `18 - decimals` underflows in unsigned arithmetic and reverts.
- Impact: `getLockedWeightedValue` underpins harvesting (`AccountManager._harvest`/`getDailySchnibbles`), plot counting (`LandManager._getNumPlots`), and several bonus calculations, so a single bad token configuration permanently reverts those paths for affected users (DoS). Requires an admin misconfiguration.
- Reviewer disagreement: none.

## Farming timestamp subtraction underflow permanently locks staked NFTs
*(minority, 1 of 6 reports)*
- Location: `src/managers/LandManager.sol` : `_farmPlots` (the `_getNumPlots(landlord) < _toiler.plotId` branch)
- Mechanism: In that branch the code substitutes `timestamp = plotMetadata[landlord].lastUpdated`, marks the toiler `dirty`, then computes `schnibblesTotal = (timestamp - _toiler.lastToilDate) * BASE_SCHNIBBLE_RATE`. If the renter staked/toiled *after* the landlord's last metadata update (`lastUpdated < lastToilDate`), the unsigned subtraction underflows and reverts; the `dirty = true` write is rolled back, so it is not self-healing.
- Impact: `_farmPlots` runs via the `forceFarmPlots` modifier on `unstakeMunchable` and `transferToUnoccupiedPlot`; because the loop reverts on the offending token, the renter can no longer farm, transfer, or unstake *any* of their munchables — the NFTs become permanently locked in LandManager. Reachable whenever a landlord reduces locked balance after a renter has staked.
- Reviewer disagreement: none. (Distinct from the off-by-one invalid-plot consensus finding, which targets the same branch's bounds check rather than the timestamp subtraction.)

## Negative-bonus farming cast bricks staked NFTs (revert / stuck position)
*(minority, 1 of 6 reports)* *(conflicting reviews: 5 of 6 reports read the same cast as a wrap/mint rather than a revert)*
- Location: `src/managers/LandManager.sol` : `_farmPlots`
- Mechanism: gpt-5.5 shot 1 claims that for `finalBonus` below ~`-1`, the signed result is negative and the `uint256(...)` cast *reverts*. Because `stakeMunchable`, `unstakeMunchable`, and `transferToUnoccupiedPlot` all force-farm first, the position becomes permanently stuck.
- Impact: A renter intentionally stakes a negatively-matched NFT/landlord combination, permanently occupying a landlord plot (denying capacity) while trapping the NFT until configuration changes — DoS / griefing.
- Reviewer disagreement: opus shots 1–3 and gpt-5.5 shots 2–3 read the identical cast as *wrapping* to ~`2²⁵⁶` (a mint, not a revert); gpt-5.5 shot 2 additionally notes a DoS can arise on the same inflated value via the `schnibblesTotal * latestTaxRate` overflow when tax is non-zero.

## Snapshot owner can burn or migrate NFTs after transferring them away
*(minority, 1 of 6 reports)*
- Location: `src/managers/MigrationManager.sol` : `burnNFTs` / `burnRemainingPurchasedNFTs` / `migratePurchasedNFTs` / `_migrateNFTs`
- Mechanism: Migration eligibility relies only on `_migrationSnapshots[keccak256(user, tokenId)]`; the code never verifies `_user`/`msg.sender` still owns the old NFT before calling `_oldNFTContract.burn(tokenId)`. Snapshot ownership becomes stale after a transfer/sale.
- Impact: A snapshot owner can sell/transfer an old NFT and later burn or migrate it anyway — the current holder loses the old NFT while the snapshot owner receives points or a newly minted migrated NFT. Precondition: old NFTs are transferable between snapshot and burn/migration.
- Reviewer disagreement: none directly on stale ownership; opus shots 1–2 defended only the *double-claim* and *msg.value atomicity* aspects of MigrationManager, which are separate from this code path.

## Munchadex transfers apply bonuses retroactively
*(minority, 1 of 6 reports)*
- Location: `src/managers/MunchadexManager.sol` : `updateMunchadex` (with `src/tokens/MunchNFT.sol` : `_update`)
- Mechanism: `updateMunchadex` mutates the sender/recipient Munchadex counters *before* calling `accountManager.forceHarvest`, so the harvest bonus calculation reads the already-updated Munchadex state and credits past elapsed time as if the recipient had owned the newly received unique NFT for the whole interval.
- Impact: An attacker leaves an account unharvested, transfers in NFTs that raise the Munchadex bonus, harvests inflated historical rewards, then transfers the NFTs away with little elapsed-time penalty.
- Reviewer disagreement: none.

## Farming corrupts landlord pet cooldown state
*(minority, 1 of 6 reports)*
- Location: `src/managers/LandManager.sol` : `_farmPlots`
- Mechanism: When crediting landlord schnibbles, `_farmPlots` writes `landlordMetadata.lastPetMunchable = uint32(timestamp)`. That field is the player's pet cooldown used by `SnuggeryManager.pet`, but farming is unrelated to petting.
- Impact: A renter with a staked munchable on the victim's land can repeatedly farm to keep refreshing the landlord's `lastPetMunchable`, preventing the landlord from ever earning pet rewards.
- Reviewer disagreement: none.

## Fee-on-transfer / rebasing tokens are over-credited when locked
*(minority, 1 of 6 reports)*
- Location: `src/managers/LockManager.sol` : `_lock`
- Mechanism: ERC-20 locks credit `lockedToken.quantity += _quantity` after `safeTransferFrom`, without measuring the actual received balance delta. A fee-on-transfer or rebasing configured token can deliver less than `_quantity` while the user is credited the full amount.
- Impact: For any such active configured token, an attacker can overstate locked value, receive excess schnibbles/NFT-reveal credit, and later attempt to withdraw more than was deposited — draining reserves from other lockers.
- Reviewer disagreement: none.

## Referral bonus points are minted outside the period's emission cap
*(minority, 1 of 6 reports)*
- Location: `src/managers/ClaimManager.sol` : `_claimPoints`
- Mechanism: On each claim, `_points[player.referrer] += _referralBonus`, but only the claimer's own `claimAmount` is added to `currentPeriod.claimed`; the referral bonus is never counted against `currentPeriod.available`/`claimed` (an inline `// TODO` acknowledges this).
- Impact: Total points per period exceed `pointsPerPeriod` by the sum of all referral bonuses, fully convertible to MUNCH via `convertPointsToTokens`. An actor registers alts naming a controlled referrer; every alt's legitimate claim mints extra uncapped points, inflating token supply beyond schedule (bounded per period, unbounded over time).
- Reviewer disagreement: none.

---

*Recall check: 6 input reports surfaced 16 distinct findings by (code path + root cause); 16 appear in this output (8 consensus + 8 minority). No findings dropped.*

