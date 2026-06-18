# Audit: 2024-05-munchables

## Consensus findings

## Pet rewards over-scaled by an extra 1e18
*(consensus)*
- Location: `src/managers/SnuggeryManager.sol` : `pet()`
- Mechanism: `PET_TOTAL_SCHNIBBLES` (configured as `10e18 / 72`) and `bonusSchnibbles` are already wei/1e18-denominated, but the split is computed as `petterSchnibbles = ((totalSchnibbles * 5) / 11) * 1e18` and `pettedSchnibbles = ((totalSchnibbles * 6) / 11) * 1e18`, multiplying an already-1e18-scaled quantity by `1e18` again. The intended "5 and 6 schnibbles per pet" becomes ~`6e34` / `~7e34`. The same inflated value is both written to `unfedSchnibbles` and emitted, so storage and event agree but both are ~1e18× too large.
- Impact: Each pet credits astronomically more `unfedSchnibbles` than intended to both petter and petted. With only a 10-minute petter cooldown / 5-minute per-munchable cooldown, any two accounts with eligible munchables can repeatedly farm essentially unlimited schnibbles, which convert into claim points and ultimately MUNCH tokens — a severe reward-inflation / economic drain.

## Migration bonus division by `(highest − weightedValue)` yields unbounded harvest bonus
*(consensus)*
- Location: `src/managers/BonusManager.sol` : `_calculateMigrationBonus()`
- Mechanism: In the partial branch the bonus is `(_migrationBonus * (weightedValue - halfAmount)) / (migrateHighestAmount - weightedValue)`. The denominator uses `weightedValue` instead of the intended fixed range (`migrateHighestAmount - halfAmount`). As `weightedValue` approaches `migrateHighestAmount` from below, the denominator approaches zero and the returned bonus grows without bound and can greatly exceed `migrationBonus`. `weightedValue` is fully attacker-controlled — it is the player's locked weighted value via `LockManager`, tunable by adjusting the locked quantity. No upper cap is applied to the returned bonus.
- Impact: During the migration-bonus window (`block.timestamp < migrationBonusEndTime`), a migrated player can lock an amount placing `weightedValue` just under `migrateHighestAmount` and obtain an enormous (effectively unbounded) harvest bonus. `getHarvestBonus` feeds directly into `AccountManager._harvest` (`dailySchnibbles += dailySchnibbles * bonus / 1e18`), so the attacker mints arbitrarily large `unfedSchnibbles`, which convert to claim points and MUNCH tokens.

## WETH yield claimed as USDB
*(consensus)*
- Location: `src/managers/RewardsManager.sol` : `_claimYieldForContract()` (the `_yieldWETH` branch)
- Mechanism: The WETH yield branch reads WETH claimable yield but calls `IERC20YieldClaimable(_contract).claimERC20Yield(address(USDB), _yieldWETH)` — passing `address(USDB)` as the token contract instead of `address(WETH)`. The contract then attempts to claim a USDB amount equal to the WETH claimable amount, while `_forwardYield` simultaneously treats `ongoingWETH` as real WETH (and `USDB.approve(...)` only covers `ongoingUSDB`). The token actually claimed never matches the bookkeeping.
- Impact: Claimable WETH yield is never properly claimed/forwarded; a spurious USDB claim of size `_yieldWETH` is attempted against the target contract, and the forwarding path can revert (insufficient USDB approval / claimable) or forward unrelated WETH already held by the manager. Because `claimYieldForContracts` is public, anyone can trigger this broken path for affected contracts, causing loss/misrouting of protocol yield and bricking yield collection whenever WETH yield is present.

## Additional findings (single-reviewer)

## ClaimManager.newPeriod — underflow bricks all future periods (excess double-counting)
*(Reviewer A only)*
- Location: `src/managers/ClaimManager.sol` : `newPeriod()` (`uint256 _excess = currentPeriod.available - currentPeriod.claimed;`) together with `_claimPoints()`
- Mechanism: In `_claimPoints`, claimable points are computed against `availablePoints = currentPeriod.available + _pointsExcess[currentPeriodId]`, and every successful claim does `currentPeriod.claimed += claimAmount`. So `claimed` accumulates against *available + carried-over excess*, while `newPeriod` later computes the new excess as `currentPeriod.available - currentPeriod.claimed` (subtracting only from `available`, which equals `pointsPerPeriod`). Once a prior period leaves unclaimed excess that is later claimed (or live `getTotalChonk` exceeds the `globalTotalChonk` snapshot taken at period start, since chonks can grow via feeding/imports mid-period), `claimed` becomes strictly greater than `available`. The next `newPeriod()` evaluates `available - claimed` on checked (0.8.x) arithmetic and reverts.
- Impact: Permanent denial of service of the entire reward-period system. Once `claimed > available` in a period, `newPeriod()` reverts forever, no new period can start, and the `onlyValidPeriod` claim path becomes unusable. Reachable in normal operation (any partially-claimed period followed by a fully-claimed one) and deliberately triggerable by a player whose chonk grew after the snapshot.

## ClaimManager._claimPoints — referral bonus minted outside the period budget
*(Reviewer A only)*
- Location: `src/managers/ClaimManager.sol` : `_claimPoints()` (the `_referralBonus` block)
- Mechanism: When a claimer has a referrer, `_points[player.referrer] += _referralBonus` is credited, but `_referralBonus` is never added to `currentPeriod.claimed` nor checked against `currentPeriod.available`. Referral points are therefore minted on top of the period's emission budget, and a player can set an arbitrary `referrer` at registration.
- Impact: Total points emitted per period exceed `pointsPerPeriod` by the sum of all referral bonuses, diluting the fixed-emission guarantee and inflating convertible points (→ MUNCH). A self-referral chain lets a player passively mint extra points on every claim. (Acknowledged by an in-code TODO, but a live inflation path.)

## BonusManager.getFeedBonus — int16→int8 / uint8→int8 truncation of configured bonuses
*(Reviewer A only)*
- Location: `src/managers/BonusManager.sol` : `getFeedBonus()` (`int8 realmBonus = int8(realmBonuses[realmIndex]);` and `int16(int8(rarityBonus))`)
- Mechanism: `realmBonuses` is stored as `int16[]` (via `setSmallIntArray`) but downcast to `int8` before use; any configured magnitude outside `[-128,127]` silently truncates and can flip sign. Likewise `rarityBonus` is a `uint8` cast to `int8`, so any value `>127` becomes negative. The resulting `sumBonuses` and `finalBonus` drive `feed()`'s chonk increment.
- Impact: For admissible (storage-type-valid) but out-of-`int8`-range configuration values, the feed bonus is computed from a corrupted/negated number, mis-crediting (or debiting) chonks on feed — skewing level-ups and the per-period point distribution. Severity depends on configured values; the downcast is a genuine silent-truncation defect in the value path.

## SignatureVerifier.recover — version check always reverts (`||` instead of `&&`)
*(Reviewer A only)*
- Location: `src/libraries/SignatureVerifier.sol` : `recover()` (`if (v != 27 || v != 28) revert InvalidSignature();`)
- Mechanism: The condition `v != 27 || v != 28` is a tautology — for any `v`, at least one inequality is true — so the function unconditionally reverts. The intended guard is `v != 27 && v != 28`. (Even if fixed, recover would still lack nonce/domain separation.)
- Impact: Any code path relying on this verifier is permanently bricked (always reverts). It is not wired into the current on-chain reveal flow (signatures are validated off-chain via the RNG proxy), so present impact is limited, but the library is unusable and dangerous if later relied upon for an access-controlled action.

## Stale lock remainders allow under-collateralized NFT reveals
*(Reviewer B only)*
- Location: `src/managers/LockManager.sol` : `_lock` / `unlock`
- Mechanism: `_lock` adds `lockedToken.remainder` to the new `_quantity` when calculating `numberNFTs`, but `unlock` only decreases `lockedToken.quantity` and never clears or reduces `lockedToken.remainder`. A user can lock just below `nftCost`, wait until unlockable, withdraw all real tokens, then lock only the missing dust amount; the stale remainder is still counted and `nftOverlord.addReveal` is called.
- Impact: An attacker can receive unrevealed NFTs without actually keeping `nftCost` worth of tokens locked. Preconditions: the lockdrop is still active when the first lock becomes unlockable.

## Lock-duration bonus is applied retroactively
*(Reviewer B only)*
- Location: `src/managers/LockManager.sol` : `setLockDuration`; `src/managers/AccountManager.sol` : `_harvest`
- Mechanism: `setLockDuration` updates `playerSettings[msg.sender].lockDuration` without first forcing a harvest at the old bonus rate. Later, `_harvest` applies the current lock-duration bonus to the entire elapsed time since `lastHarvestDate`.
- Impact: A user can wait with a low or zero duration bonus, increase the lock duration immediately before harvesting, and receive the higher bonus for past time that was not actually locked under that duration.

## Munchadex bonus changes are harvested after state mutation
*(Reviewer B only)*
- Location: `src/managers/MunchadexManager.sol` : `updateMunchadex`
- Mechanism: `updateMunchadex` increments or decrements Munchadex counters before calling `accountManager.forceHarvest`. Because harvest bonus calculation reads the already-mutated Munchadex state, the new bonus or penalty is applied to the entire prior accrual interval.
- Impact: An attacker can move a bonus-completing NFT from a low-value account to a high-locked-value account immediately before harvest and receive the Munchadex bonus retroactively for the whole elapsed period.

## Old NFT ownership is not checked during migration or burn
*(Reviewer B only)*
- Location: `src/managers/MigrationManager.sol` : `_migrateNFTs`, `burnNFTs`, `burnRemainingPurchasedNFTs`
- Mechanism: Migration eligibility is based only on snapshot data keyed by `_user` and `tokenId`. The contract then calls `_oldNFTContract.burn(tokenId)` without checking that `_user` still owns the old NFT at execution time. `OldMunchNFT.burn` allows the MigrationManager to burn any token ID.
- Impact: A snapshot owner can transfer or sell an old NFT after the snapshot, then later migrate or burn it to receive the new NFT or points while destroying the current holder's old NFT. Preconditions: old NFTs remain transferable after the migration snapshot.

## Fee-on-transfer or false-returning ERC20s are overcredited
*(Reviewer B only)*
- Location: `src/managers/LockManager.sol` : `_lock` / `unlock`
- Mechanism: ERC20 `transferFrom` and `transfer` return values are ignored, and the contract does not compare pre/post balances. `lockedToken.quantity` is increased by `_quantity` even if the token transfers less due to fees or returns `false` without reverting.
- Impact: If such a token is configured as active, an attacker can receive more locked credit than the contract actually received and later withdraw against that inflated accounting, draining other token balances or making the lock insolvent.

