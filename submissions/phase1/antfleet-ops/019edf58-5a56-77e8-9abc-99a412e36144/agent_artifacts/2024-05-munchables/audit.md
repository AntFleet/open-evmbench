# Audit: 2024-05-munchables

## SignatureVerifier `v` Validation Always Reverts
- Location: `src/libraries/SignatureVerifier.sol` : `recover`
- Mechanism: The check `if (v != 27 || v != 28)` uses OR instead of AND. For any `v`, either `v != 27` or `v != 28` is true, so the condition is always true and every call reverts. Signatures can never be verified.
- Impact: Any feature relying on this verifier is completely broken (denial of service). Note this library isn't wired into the shown contracts but is provided as part of the audited codebase.

## Missing Access Control on `claimYieldForContracts` / `claimGasFeeForContracts`
- Location: `src/managers/RewardsManager.sol` : `claimYieldForContracts`, `claimGasFeeForContracts`
- Mechanism: Both functions are public/external with no `onlyRole`, `onlyAdmin`, or `notPaused` modifier (the commented-out versions were restricted to `Role.ClaimYield`). Anyone may call them supplying arbitrary `_contracts`.
- Impact: Any caller can force the RewardsManager to claim yield/gas from arbitrary registered collector contracts and forward it to the configured distributors/treasury. Worse, because `_claimYieldForContract` calls `IERC20YieldClaimable(_contract).claimERC20Yield(...)` on any address supplied by the caller, an attacker can direct arbitrary external calls from RewardsManager to any contract, enabling griefing/phishing of Blast yield configuration and premature yield extraction.

## `claimERC20Yield` Claims Wrong Token
- Location: `src/managers/RewardsManager.sol` : `_claimYieldForContract`
- Mechanism: For WETH yield the code calls `IERC20YieldClaimable(_contract).claimERC20Yield(address(USDB), _yieldWETH);` — it passes the USDB address instead of the WETH address.
- Impact: WETH yield is never actually claimed from the collector; the collector is instructed to claim USDB instead. Yield accounting is corrupted and WETH yield may be permanently stuck or misrouted.

## `getRole`/`onlyOneOfRoles`/`onlyRole` Are Caller-Context Dependent
- Location: `src/config/ConfigStorage.sol` : `getRole`; used by `BaseConfigStorage.onlyRole`/`onlyOneOfRoles`
- Mechanism: `getRole(_role)` returns `getContractRole(_role, msg.sender)`. When a manager contract calls `configStorage.getRole(...)`, `msg.sender` inside ConfigStorage is the manager, not the original user. So `onlyRole(Role.Admin)` etc. compare the user against a per-contract role slot keyed by the manager address, not the universal admin. Only `getUniversalRole` checks the global role.
- Impact: Role checks via `onlyRole`/`onlyOneOfRoles` (e.g. `onlyAdmin` in `BaseConfigStorage`, `setUSDThresholds`/`configureLockdrop`/`configureToken` in LockManager, `newPeriod` in ClaimManager, `setTokenURI` in MunchNFT, RNG oracle role) can silently pass or fail depending on per-contract role configuration, breaking access control. A misconfigured per-contract role entry can let unauthorized users perform admin actions, or block the real admin.

## `onlyConfiguredContract2` Permits `address(0)` Senders
- Location: `src/config/BaseConfigStorage.sol` : `onlyConfiguredContract2`
- Mechanism: The modifier allows execution if `configuredContract == msg.sender || configuredContract2 == msg.sender`. If either configured address is `address(0)` and `msg.sender` is `address(0)` (impossible in practice) it would pass, but more importantly the zero-address error checks are only reached inside the `else` branch; if one key maps to zero and the other to the caller, the check still passes. Combined with the fact that many config keys default to zero, calls can bypass the intended "must be configured and authorized" invariant when one of the two keys is unset.
- Impact: Functions gated by `onlyConfiguredContract2` (e.g. `forceHarvest`, `updatePlayer`) can be invoked by a configured contract even when the second intended contract is unconfigured, leading to unexpected authorization paths.

## `forceHarvest` Can Be Called by Any Munchadex-Configured Caller Context
- Location: `src/managers/AccountManager.sol` : `forceHarvest` / `MunchadexManager.updateMunchadex`
- Mechanism: `forceHarvest` is gated by `onlyConfiguredContract2(LockManager, MunchadexManager)`. `MunchadexManager.updateMunchadex` calls `accountManager.forceHarvest(_from)`/`(_to)` for arbitrary `_from`/`_to` supplied via NFT transfers. Because `updateMunchadex` is invoked from `MunchNFT.transferFrom`, any user transferring an NFT can cause `forceHarvest` to run on arbitrary addresses (`from`/`to` of the transfer).
- Impact: An attacker can force harvest on arbitrary players at arbitrary times, resetting their `lastHarvestDate` and causing them to lose unharvested schnibbles (griefing/DoS and accounting manipulation).

## `_harvest` Time Math Underflow / Negative Time
- Location: `src/managers/AccountManager.sol` : `_harvest`
- Mechanism: `secondsToClaim = block.timestamp - players[_caller].lastHarvestDate;` with no check that `lastHarvestDate <= block.timestamp`. If a player's `lastHarvestDate` is set to a future value (possible via `updatePlayer` by SnuggeryManager/PrimordialManager, or via manipulation of forced harvests), the subtraction underflows in 0.8 (reverts) — but more importantly, since `lastHarvestDate` is a `uint32` and `block.timestamp` is cast down elsewhere, future timestamps can be persisted, permanently bricking harvest for that account.
- Impact: Griefing: set a player's `lastHarvestDate` to the future so they can never harvest again (revert-on-underflow), or to the past to grant unbounded schnibbles.

## `getDailySchnibbles` Uses Caller Instead of Main Account
- Location: `src/managers/AccountManager.sol` : `getDailySchnibbles` / `_harvest`
- Mechanism: `getDailySchnibbles(_caller)` calls `lockManager.getLockedWeightedValue(_caller)` directly with the passed address, but `_harvest` passes `_caller = _getMainAccountRequireRegistered(...)`. When a sub-account calls `harvest()`, `_harvest` resolves to the main account and calls `getDailySchnibbles(mainAccount)` — OK — but `getDailySchnibbles` is also `public` and used externally with arbitrary `_caller`. The public function returns data for any address without resolving to the main account.
- Impact: Inconsistent accounting: sub-accounts querying `getDailySchnibbles` get zero bonus/value (because locks are stored against the main account), and any external caller can probe any account's locked value. Can cause incorrect UI/oracle data and wrong harvest calculations if invoked with a sub-account elsewhere.

## `getLockedWeightedValue` Reverts on Token Decimals > 18
- Location: `src/managers/LockManager.sol` : `getLockedWeightedValue`
- Mechanism: `deltaDecimal = 10 ** (18 - configuredTokens[...].decimals)`. If a configured token has `decimals > 18`, the exponent is negative and the `**` operation reverts (underflow in 0.8).
- Impact: Any configured token with >18 decimals makes `getLockedWeightedValue` revert for all players, breaking harvest, bonuses, and claim logic system-wide.

## `setLockDuration` Allows Setting `unlockTime` Far Into the Future Without Re-Checking Max
- Location: `src/managers/LockManager.sol` : `setLockDuration`
- Mechanism: `setLockDuration` enforces `MaxLockDuration` on `_duration`, but updates existing locks' `unlockTime = lastLockTime + _duration` without verifying that `lastLockTime + _duration` is within `MaxLockDuration` from `block.timestamp`. Since `lastLockTime` can be in the past, the new unlock time can exceed `block.timestamp + MaxLockDuration`.
- Impact: Players can extend their lock far beyond the advertised maximum duration (up to `lastLockTime + MaxLockDuration`, which could be less than current time — but if `lastLockTime` is recent and they keep bumping, they can lock beyond max), manipulating harvest/lock bonus calculations that depend on `lockDuration`.

## `setLockDuration` Stores `lockDuration` Even When Lock Is Not Active
- Location: `src/managers/LockManager.sol` : `setLockDuration`
- Mechanism: The function sets `playerSettings[msg.sender].lockDuration = uint32(_duration)` and only updates `unlockTime` for tokens currently locked. There is no lower bound and no tie to `lockdrop.minLockDuration` outside the lockdrop window.
- Impact: Users can set arbitrarily small/zero durations to maximize bonus formula outcomes or to game `_calculateLockBonus` (which is pure on `lockDuration`). Bonus accounting can be inflated because the lock bonus depends only on the stored `lockDuration`, not on actual remaining lock time.

## `migratePurchasedNFTs` Payment Check Uses Wrong Token
- Location: `src/managers/MigrationManager.sol` : `migratePurchasedNFTs`
- Mechanism: The function accumulates `quantity` in ETH (`purchasedUnlockPrice` per token) and requires `msg.value == (quantity * discountFactor) / 10e12`, but then calls `_migrateNFTs(msg.sender, address(0), tokenIds)` which itself calls `_lockManager.lockOnBehalf{value: quantity}(...)` where `quantity = (totalLockAmount * discountFactor) / 10e12`. The `msg.value` is sent by the user, but `_migrateNFTs` forwards `quantity` to `lockOnBehalf` — these two `quantity` calculations are duplicated and can diverge if `_migrateNFTs`'s `totalLockAmount` includes additional tokens (it iterates `tokenIds` again and sums `purchasedUnlockPrice`). If a `tokenId` is 0 or `claimed`, `migratePurchasedNFTs`'s loop skips it for the payment calc, but `_migrateNFTs` also skips it — consistent only if both skip identically. The bigger issue: `_migrateNFTs` will revert in `lockOnBehalf` if `msg.value != _quantity`, but `msg.value` in that internal call is the whole `msg.value` of the outer call, not the recomputed `quantity`. If they differ, the call reverts; if they happen to match, fine — but the duplicated arithmetic is fragile and the validation is effectively done by the inner revert, not by the explicit check.
- Impact: Broken migration flow / potential payment bypass when the two `quantity` calculations diverge due to filtering differences (e.g., `tokenId == 0` handling), or DoS of legitimate migrations.

## `lockFundsForAllMigration` Does Not Lock the Funds
- Location: `src/managers/MigrationManager.sol` : `lockFundsForAllMigration`
- Mechanism: The function transfers `totalLockAmount` from the user to `MigrationManager` (via `msg.value` or `transferFrom`) and sets `_userLockedAction = LOCKED_FULL_MIGRATION`, but never locks those funds with `LockManager`. The actual locking only happens later inside `_migrateNFTs` (called from `migrateAllNFTs`), which recomputes `totalLockAmount` from the snapshots being migrated and calls `lockOnBehalf` with `quantity = (totalLockAmount * discountFactor) / 10e12`. But `lockFundsForAllMigration` already required `msg.value == totalLockAmount` (which already includes `discountFactor` via `getUserMigrateQuantityAll`). The funds collected here are then locked again from the contract balance, but the amounts are computed differently (`getUserMigrateQuantityAll` sums all locked amounts; `_migrateNFTs` sums only the migrated batch). Since `migrateAllNFTs` processes in batches of `SKIP_AMOUNT`, only a portion is locked per batch, but the full discounted amount was already collected up-front.
- Impact: Discrepancy between collected funds and locked funds; ETH/tokens can be stranded in MigrationManager, or users may be charged the full discounted amount up front but only partial locks occur, enabling accounting errors and potential fund loss.

## `migrateAllNFTs` Calls `lockOnBehalf` with Wrong ETH Value
- Location: `src/managers/MigrationManager.sol` : `_migrateNFTs` (via `migrateAllNFTs`)
- Mechanism: `migrateAllNFTs` is not `payable` and not `nonReentrant`. It calls `_migrateNFTs(_user, tokenLocked, tokenIds)` which calls `_lockManager.lockOnBehalf{value: quantity}(...)` for `tokenLocked == address(0)`. The `quantity` is `totalLockAmount * discountFactor / 10e12` for this batch. But `migrateAllNFTs` forwarded no ETH (not payable), so `address(this).balance` must already contain enough from `lockFundsForAllMigration`. There is no check that the contract holds sufficient balance for the batch's `quantity`, and multiple batches will each try to send `quantity` from the contract balance.
- Impact: If the contract balance is insufficient (e.g., due to the upfront collection mismatch above), migrations revert; if it's excessive, leftover ETH is stranded. Reentrancy is also unguarded on `migrateAllNFTs`.

## `migrateAllNFTs` Lacks Reentrancy Protection
- Location: `src/managers/MigrationManager.sol` : `migrateAllNFTs`, `burnNFTs`, `burnRemainingPurchasedNFTs`
- Mechanism: Only `lockFundsForAllMigration` and `migratePurchasedNFTs` are `nonReentrant`. `migrateAllNFTs`, `burnNFTs`, and `burnRemainingPurchasedNFTs` are not, yet they perform external calls (`_oldNFTContract.burn`, `_nftOverlord.mintForMigration`, `_lockManager.lockOnBehalf`, `_claimManager.burnNFTsForPoints`) and mutate `_migrationSnapshots[key].claimed`.
- Impact: A malicious old NFT contract (or reentrancy via mint callbacks) could re-enter to claim the same snapshot multiple times or manipulate `_userLockedAction`, minting duplicate NFTs or double-counting points.

## `burnNFTs` Sets `_userLockedAction = LOCKED_BURN` Even When Nothing Burned
- Location: `src/managers/MigrationManager.sol` : `burnNFTs`
- Mechanism: `burnNFTs` unconditionally sets `_userLockedAction[_user] = UserLockedChoice.LOCKED_BURN` after the loop, even if every snapshot in the batch was `claimed` or had `lockAmount == 0` and was skipped (nothing burned). Same issue in `burnRemainingPurchasedNFTs` setting `_userPurchasedAction`.
- Impact: A caller (or anyone, since `burnNFTs` has no caller-vs-`_user` check beyond the `SelfNeedsToChooseError` path) can lock a user into `LOCKED_BURN` without actually burning anything, preventing them from ever doing `LOCKED_FULL_MIGRATION` afterward. Griefing/DoS.

## `burnNFTs` / `migrateAllNFTs` Authorization Bypass
- Location: `src/managers/MigrationManager.sol` : `burnNFTs`, `migrateAllNFTs`, `burnRemainingPurchasedNFTs`
- Mechanism: `burnNFTs(_user, _skip)` only reverts if `_user != msg.sender && _userLockedAction[_user] == NONE`. If `_userLockedAction[_user]` has been set to anything (including `LOCKED_BURN` via the bug above, or `LOCKED_FULL_MIGRATION`), any third party may call `burnNFTs` on behalf of `_user`. Similarly `migrateAllNFTs(_user, _skip)` has no `msg.sender == _user` check at all — anyone can trigger migration for any user who has locked funds.
- Impact: Attackers can force-burn or force-migrate another user's NFTs, destroying their NFTs and locking their funds without consent.

## `lockOnBehalf` Accepts Arbitrary `_onBehalfOf` Without Authorization
- Location: `src/managers/LockManager.sol` : `lockOnBehalf`
- Mechanism: `lockOnBehalf` lets a caller lock their own tokens on behalf of any `_onBehalfOf` address. It pulls tokens from `msg.sender` and sets `lockedTokens[_onBehalfOf]` and `playerSettings[_onBehalfOf].lockDuration`. There is no requirement that `msg.sender` is authorized by `_onBehalfOf`.
- Impact: An attacker can lock tokens on behalf of a victim, setting/expiring the victim's `unlockTime` and `lockDuration`, and forcing `accountManager.forceHarvest(_onBehalfOf)` (griefing the victim's harvest). The attacker's tokens become locked in the victim's name (attacker loses tokens), but the victim's accounting/bonuses are corrupted.

## `lock`/`lockOnBehalf` Not Restricted to Lockdrop Window for NFT Awards
- Location: `src/managers/LockManager.sol` : `_lock`
- Mechanism: NFT reveals (`nftOverlord.addReveal`) are only granted when `lockdrop.start <= now <= lockdrop.end`, but locking itself is allowed any time. After lockdrop ends, users can still lock tokens (no NFT reward) but `forceHarvest` and bonus calculations still apply. There is no check that lockdrop is active before allowing `_lock`.
- Impact: Design inconsistency; not necessarily a vulnerability, but if the intent was lockdrop-only locking, this bypasses it.

## `getLevelThresholds` Can Revert / Misreport at Boundaries
- Location: `src/libraries/MunchablesCommonLib.sol` : `getLevelThresholds`
- Mechanism: When `_chonk` is between `levelThresholds[0]` and `levelThresholds[99]`, the binary search returns `_currentLevelThreshold = levelThresholds[answer - 1]`. If `answer == 0` (which shouldn't happen given the `< levelThresholds[0]` early return, but the search can set `answer = 0` when `low == 0` and `high` becomes 0), `answer - 1` underflows and reverts in 0.8. More critically, the function assumes `levelThresholds.length >= 100`; if the configured array is shorter, `levelThresholds[99]` reverts.
- Impact: Misconfigured level thresholds cause reverts in `NFTOverlord.getLevelUpData` and `munchableFed`, breaking feeding/level-up system-wide.

## `getLevelThresholds` Returns Wrong Threshold
- Location: `src/libraries/MunchablesCommonLib.sol` : `getLevelThresholds`
- Mechanism: The binary search finds the smallest index `answer` such that `levelThresholds[answer] > _chonk`, then returns `_currentLevel = answer + 1` and `_currentLevelThreshold = levelThresholds[answer - 1]`. The "current level threshold" should be the threshold the player passed to reach their current level, i.e., `levelThresholds[answer - 1]` is the threshold for level `answer` — but the returned level is `answer + 1`. The threshold-to-level mapping is off by one.
- Impact: Incorrect level calculations; NFTs may level up at wrong chonk thresholds, inflating/deflating game attributes and bonus computations.

## `SnuggeryManager.getSnuggery` Returns Wrong Array Indices
- Location: `src/managers/SnuggeryManager.sol` : `getSnuggery`
- Mechanism: The function allocates `_snuggery` of size `maxSize` (≤10) but then loops `for (i = _start; i < maxSize + _start; i++)` and assigns `_snuggery[i] = ...` using `i` as the destination index. When `_start > 0`, `i` exceeds the array bounds (`maxSize`), causing an out-of-bounds array write which reverts in 0.8.
- Impact: Calling `getSnuggery` with `_start > 0` always reverts; pagination is broken. Any consumer using `_start` (e.g., `AccountManager.getFullPlayerData` uses `_start=0`, so OK there, but the public interface is broken).

## `SnuggeryManager.exportMunchable` Transfers Before Removing, Reentrancy
- Location: `src/managers/SnuggeryManager.sol` : `exportMunchable`
- Mechanism: `exportMunchable` calls `erc721Token.transferFrom(address(this), _caller, _tokenId)` before removing the token from the `snuggeries[_caller]` array. The `chonkUpdated` modifier calls `forceClaimPoints` before and `_recalculateChonks` after, but the NFT transfer can trigger callbacks (ERC721 receiver) to the caller before the snuggery array is cleaned up.
- Impact: A malicious receiver could re-enter `importMunchable`/`exportMunchable`/`feed`/`pet` while the snuggery state is inconsistent (token still present in array but no longer owned by the contract), enabling duplicate entries or corrupted chonk accounting.

## `SnuggeryManager.pet` Applies Petter Bonus to Both Shares
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: `bonusSchnibbles = (PET_TOTAL_SCHNIBBLES * bonusPercent) / 1e18` based on the petter's lock bonus, then `totalSchnibbles = PET_TOTAL_SCHNIBBLES + bonusSchnibbles`, and both `petterSchnibbles` and `pettedSchnibbles` are derived from `totalSchnibbles`. The bonus is applied to both the petter and the petted.
- Impact: The petter's lock bonus inflates the petted recipient's reward too. If intended, fine; if not, this is an accounting error that lets a high-bonus petter gift arbitrarily large schnibbles to other accounts (up to `PET_TOTAL_SCHNIBBLES * (1 + bonusPercent)`), inflating the petted account's schnibbles.

## `SnuggeryManager.pet` Does Not Verify Token Owner
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: `pet` checks `_findSnuggeryIndex(_pettedOwner, _tokenId)` but never verifies that the NFT with `_tokenId` actually belongs to `_pettedOwner` in the snuggery — only that `_tokenId` appears in `_pettedOwner`'s snuggery array. Since the snuggery array stores token IDs imported by the owner, this is implicitly OK, but the `lastPettedTime` is updated on `_tokenId` regardless of which owner's snuggery it's in. Combined with the export/import reentrancy above, an attacker could pet a token that was just exported.
- Impact: Potential to pet tokens no longer in the petted owner's snuggery during reentrancy, awarding schnibbles incorrectly.

## `SnuggeryManager.increaseSnuggerySize` Integer Overflow on `maxSnuggerySize`
- Location: `src/managers/SnuggeryManager.sol` : `increaseSnuggerySize`
- Mechanism: `_player.maxSnuggerySize += uint16(_quantity);` with no check that the result fits in `uint16` or that `_quantity > 0`. In 0.8 this reverts on overflow, but an attacker can still call with large `_quantity` to revert-DoS, or with `_quantity` that overflows `uint16` to brick the function. Also no upper bound on snuggery size, so `snuggeries` arrays can grow unbounded, causing `getTotalChonk`/`_recalculateChonks` loops to exceed block gas.
- Impact: Unbounded snuggery size lets a user make their snuggery array arbitrarily large, then any function iterating it (`_recalculateChonks`, `getTotalChonk`, `getSnuggery`) will hit gas limits, griefing themselves or the global chonk accounting.

## `ClaimManager._claimPoints` Referral Bonus Added Without `claimed` Accounting
- Location: `src/managers/ClaimManager.sol` : `_claimPoints`
- Mechanism: `_points[player.referrer] += _referralBonus;` is added to the referrer's points, but `_referralBonus` is not added to `currentPeriod.claimed`. The `claimed` counter only tracks `claimAmount`. The referral bonus effectively mints points outside the period's `available` cap.
- Impact: Total points minted can exceed `available + excess` for a period, inflating token supply beyond intended emissions. A user with many referrals can drain the period's allocation and beyond.

## `ClaimManager._claimPoints` Sets `_lastClaimPeriod` Even When No Points Claimed
- Location: `src/managers/ClaimManager.sol` : `_claimPoints`
- Mechanism: The function sets `_lastClaimPeriod[_player] = currentPeriodId` outside the `if (_lastClaimPeriod[_player] < currentPeriodId)` block, so even if `claimAmount == 0` or the player already claimed, `_lastClaimPeriod` is updated to the current period. The `if (claimAmount > 0)` block also updates it inside. A player who calls `claimPoints` mid-period (with 0 chonk) then gains chonk later cannot claim for that period because `_lastClaimPeriod` was already advanced.
- Impact: Players who claim early (with zero or low chonk) forfeit the rest of the period's points. Griefing/self-sabotage and accounting unfairness.

## `ClaimManager.convertPointsToTokens` Minting Math
- Location: `src/managers/ClaimManager.sol` : `convertPointsToTokens`
- Mechanism: `_tokensToMint = (_pointsToConvert * _pointsPerToken) / 1e12;`. The naming is inverted — `_pointsPerToken` suggests "points per token," so the formula should be `_pointsToConvert / _pointsPerToken`. Multiplying instead of dividing mints `pointsPerToken²`-scaled tokens.
- Impact: If `_pointsPerToken` is set as "points per token" (e.g., 1000 points = 1 token), users receive `points * 1000 / 1e12` tokens instead of `points / 1000`, which is either negligible or wildly inflated depending on config. Token supply accounting is broken.

## `AccountManager.execSprayProposal` Has No Approval/Proposer Validation
- Location: `src/managers/AccountManager.sol` : `execSprayProposal`
- Mechanism: `execSprayProposal` is gated by `SocialApproval_*` roles but doesn't verify the proposer's identity or that the proposal was actually created by an authorized Social role. It also doesn't clear `_tempSprayPlayerCheck` after use (storage pollution). Anyone with an approval role can execute any stored proposal, and the proposal may have been created by a since-rotated Social role.
- Impact: Stale or unauthorized proposals can be executed; `_tempSprayPlayerCheck` leftovers corrupt future `spraySchnibblesPropose` duplicate checks (a player from a previous proposal remains `true`, causing false `DuplicateSprayerError`).

## `AccountManager.spraySchnibblesPropose` `_tempSprayPlayerCheck` Storage Pollution
- Location: `src/managers/AccountManager.sol` : `spraySchnibblesPropose`
- Mechanism: `_tempSprayPlayerCheck[_players[i]] = false;` is set at the start, then `= true` in the loop, but is never reset to `false` after the proposal is created/executed/deleted. The mapping persists across transactions.
- Impact: Future proposals that include a previously-included player will hit `DuplicateSprayerError` because the mapping still reads `true`. Over time, more and more addresses become unusable in sprays — progressive DoS of the spray feature.

## `AccountManager.register` Bypasses Sub-Account Ownership Check
- Location: `src/managers/AccountManager.sol` : `register`
- Mechanism: `register` is `onlyUnregistered(msg.sender)`. If `msg.sender` is currently a sub-account (`mainAccounts[msg.sender] != 0`), it calls `_removeSubAccount(mainAccounts[msg.sender], msg.sender)` to detach, then registers `msg.sender` as a new main account. There's no check that the user wants to "promote" — any sub-account can unilaterally become a main account, abandoning its sub-account relationship and its main account's snuggery/schnibble access.
- Impact: Sub-accounts can escape and register as independent main accounts, which may be unintended; referral/sub-account accounting is bypassed.

## `MunchadexManager.updateMunchadex` Calls `forceHarvest` on NFT Transfers
- Location: `src/managers/MunchadexManager.sol` : `updateMunchadex`
- Mechanism: On every NFT transfer (via `MunchNFT.transferFrom`), `updateMunchadex` calls `accountManager.forceHarvest(_from)` / `forceHarvest(_to)` whenever a unique species count changes. Since `forceHarvest` is also callable via `MunchadexManager` (`onlyConfiguredContract2`), this is "authorized," but it lets any user transferring an NFT force-harvest arbitrary `from`/`to` addresses.
- Impact: Griefing: transferring an NFT to/from a victim resets their `lastHarvestDate`, causing them to lose pending schnibbles if they hadn't harvested.

## `MunchNFT.transferFrom` Overrides Public Transfer Without Approval Re-Check
- Location: `src/tokens/MunchNFT.sol` : `transferFrom`
- Mechanism: `transferFrom` is overridden to call `munchadexManager.updateMunchadex(from, to, tokenId)` before `super.transferFrom`. The `super.transferFrom` (ERC721) performs the approval/ownership checks, so security is preserved there, but `updateMunchadex` runs first and mutates Munchadex state (and triggers `forceHarvest`) before the transfer is validated.
- Impact: If the transfer later reverts, the state changes are rolled back (atomic), so no direct exploit — but the `forceHarvest` side-effect executes within the same transaction even on failed transfers (rolled back), so it's safe. However, the override does not call `_update`-based hooks; `safeTransferFrom`/`_transfer` paths may bypass `updateMunchadex` since only `transferFrom` is overridden, not `_update`.
- Impact (real): ERC721's internal `_transfer` (used by `safeTransferFrom` and `_mint`/`_burn`) does not go through the overridden `transferFrom`, so transfers via `safeTransferFrom` skip `updateMunchadex` entirely, desyncing the Munchadex.

## `ConfigStorage.setRole` Has No Zero-Address Check
- Location: `src/config/ConfigStorage.sol` : `setRole`, `setUniversalRole`, `setAddress`, `setAddresses`
- Mechanism: Roles and addresses can be set to `address(0)`. Combined with `onlyRole`/`onlyAdmin` checks comparing against `getRole(...)`, a zero role silently disables access controls (since `msg.sender` is never zero). But `setAddress` for key contracts (e.g., `LockManager`, `AccountManager`) being set to zero would brick the system.
- Impact: Owner misconfiguration can permanently lock out admin functions or brick dependent contracts; no guardrails.

## `ConfigStorage.notify` Can Be Griefed / Unbounded Loop
- Location: `src/config/ConfigStorage.sol` : `notify`, `manualNotify`
- Mechanism: `notify()` loops over all `notifiableAddresses` and calls `configUpdated()` on each. If the list grows large, any `set*` with `_notify=true` will exceed block gas and revert, bricking configuration updates.
- Impact: Adding too many notifiable addresses (owner-controlled, but could be a mistake) DoSes all `set*` with notify. Also, a single malicious/failing notifiable contract reverts the entire `notify`, blocking config updates for all other contracts.

## `BaseBlastManager.setBlastGovernor` Silently Returns When Blast Not Set
- Location: `src/managers/BaseBlastManager.sol` : `setBlastGovernor`
- Mechanism: `if (address(blastContract) == address(0)) return;` silently skips setting the governor. If `blastContract` isn't configured yet when `rewardsManagerAddress` is set, the governor is never configured, but `_governorConfigured` is still set to `_governor` after the early return.
- Impact: `_governorConfigured` is recorded as the RewardsManager even though Blast was never told. Later, `reassignBlastGovernor` logic and `getConfiguredGovernor` will report a governor that Blast doesn't recognize, breaking yield/gas claiming and governor reassignment.

## `BaseBlastManager.__BaseBlastManager_reconfigure` Configures Points Operator Only Once
- Location: `src/managers/BaseBlastManager.sol` : `__BaseBlastManager_reconfigure`
- Mechanism: `if (_pointsOperatorConfigured == address(0))` gates `configurePointsOperator`. Once set, the operator can never be updated via reconfigure. Also, `configurePointsOperator` is called on every manager contract independently, but the guard means only the first reconfigure applies.
- Impact: Inability to rotate Blast Points operator; misconfiguration is permanent for that contract.

## `BaseBlastManager.claimERC20Yield` Has No Amount Validation
- Location: `src/managers/BaseBlastManager.sol` : `claimERC20Yield`
- Mechanism: The RewardsManager (authorized) can call `claimERC20Yield(token, amount)` with an arbitrary `amount`, which calls `IERC20Rebasing(token).claim(rewardsManager, amount)`. There's no check that `token` is USDB/WETH or that `amount` matches actual claimable yield.
- Impact: Since `claimYieldForContracts` is permissionless (see above), an attacker can direct claims of arbitrary amounts/tokens to the RewardsManager, potentially draining rebasing token balances or triggering unexpected behavior on fake "rebasing" tokens.

## `MigrationManager._migrateNFTs` Locks with `address(0)` Token and Discounted ETH
- Location: `src/managers/MigrationManager.sol` : `_migrateNFTs`
- Mechanism: For `_tokenLocked == address(0)`, the code calls `_lockManager.lockOnBehalf{value: quantity}(address(0), quantity, _user)`. `quantity = (totalLockAmount * discountFactor) / 10e12`. But `totalLockAmount` here sums `purchasedUnlockPrice` (2 ether) for purchased NFTs plus `lockAmount` for locked NFTs — mixing ETH-amount and token-amount semantics. For locked tokens that were originally USDB/WETH, `totalLockAmount` is in token units, but the branch only runs for `_tokenLocked == address(0)`, so locked USDB/WETH NFTs shouldn't reach here. Still, the `discountFactor` is applied twice in some flows (`getUserMigrateQuantityAll` already applies it for `lockFundsForAllMigration`, then `_migrateNFTs` applies it again).
- Impact: Double application of `discountFactor` leads to users locking far less than intended, or ETH mismatches causing reverts/fund loss.

## `PrimordialManager.feedPrimordial` Overfeed Refund Calculation
- Location: `src/managers/PrimordialManager.sol` : `feedPrimordial`
- Mechanism: When `primordials[_mainAccount].chonks > primordialLevels[0]`, the code computes `_schnibbles -= (chonks - primordialLevels[0])` and clamps `chonks = primordialLevels[0]`. But `_schnibbles` is a function parameter (memory); the subtraction only affects the local variable used later for `unfedSchnibbles -= _schnibbles`. If `chonks - primordialLevels[0] > _schnibbles`, the subtraction underflows and reverts (0.8). If the player feeds a small amount that overshoots the cap by more than the feed amount, the transaction reverts.
- Impact: Players near the cap cannot feed small amounts without reverting; griefing/DoS of primordial feeding near max level.

## `PrimordialManager` Level-Up Loop Can Run Unbounded
- Location: `src/managers/PrimordialManager.sol` : `feedPrimordial`
- Mechanism: The `while` loop increments `nextLevel` while `primordialLevels[nextLevel + 1] <= chonks && primordialLevels[nextLevel + 1] > 0 && nextLevel < 1`. With only 3 configured thresholds, the loop is bounded, but if `primordialLevels` is misconfigured (e.g., all zeros), the `> 0` guard prevents iteration — OK. However, `primordialLevels[nextLevel + 1]` when `nextLevel == 1` reads `primordialLevels[2]`, which is valid; when `nextLevel == 0`, reads `primordialLevels[1]`. The guard `nextLevel < 1` stops at 0. Logic seems OK but the `chonks > primordialLevels[0]` clamp uses `primordialLevels[0]` which is the threshold for level 0 — if unconfigured (0), the clamp sets chonks to 0, wiping all fed schnibbles.
- Impact: If `PrimordialLevelThresholds` is misconfigured, feeding can wipe chonks or revert.

## `NFTOverlord.reveal` Does Not Decrement `unrevealedNFTs` Consistently
- Location: `src/overlords/NFTOverlord.sol` : `startReveal`, `reveal`
- Mechanism: `startReveal` decrements `unrevealedNFTs` and increments `revealQueue`, then requests RNG. `reveal` (called by RNG) only decrements `revealQueue`. If the RNG callback never fires (e.g., API3 failure, or self-hosted oracle withholds), the NFT is permanently lost: `unrevealedNFTs` is decremented, `revealQueue` stays incremented, and the user cannot reveal again if `revealQueue >= MAX_REVEAL_QUEUE`.
- Impact: Lost NFTs and DoS if RNG callback fails or is withheld; no recovery/timeout mechanism.

## `NFTOverlord` Reveal Index Collision
- Location: `src/overlords/NFTOverlord.sol` : `startReveal`
- Mechanism: `revealIndex = uint256(uint160(_mainAccount)) | (uint256(revealNonce[_mainAccount]) << 160);`. The `revealNonce` is `uint96`, shifted left 160 bits — but `uint160(_mainAccount)` already occupies the low 160 bits, and the nonce occupies bits 160-255. This is unique per (account, nonce). However, in `BaseRNGProxy`, `requests[_index]` is keyed by this 256-bit index. The API3 RNGProxy maps `requestId -> _index`. If two different accounts ever produce the same `_index` (they won't, due to the address bits), collision. OK. But `mintFromPrimordial` uses `uint256(uint160(_player))` as the index with no nonce — if a player hatches a primordial while a previous primordial-reveal request is still pending, the same index is reused, overwriting the prior `requests[_index]` entry.
- Impact: A player can overwrite their own pending primordial RNG request by calling `mintFromPrimordial` again (blocked by `hatched` flag after first, but the first request is still pending until RNG returns). Repeated `mintFromPrimordial` is blocked, so probably safe — but if `revealFromPrimordial` fails/withholds, the player is stuck with `revealQueue` permanently incremented and no way to retry.

## `RNGProxySelfHosted.provideRandom` Has No Request Existence/Uniqueness Check
- Location: `src/rng/RNGProxySelfHosted.sol` : `provideRandom`
- Mechanism: `provideRandom(_index, _rand)` is `onlyRole(Role.NFTOracle)` and calls `_callback`, which checks `data.targetContract != address(0)`. But there's no rate-limiting or binding to a specific request — the oracle can supply random bytes for any pending `_index` at any time, and can front-run or choose which request to fulfill.
- Impact: A malicious/compromised NFTOracle can selectively fulfill or withhold randomness, griefing reveals/level-ups, or supply biased randomness (no commit-reveal or external verification).

## `MigrationManager` `_userLockedAmounts.tokenLocked` Overwritten by Multiple Tokens
- Location: `src/managers/MigrationManager.sol` : `loadMigrationSnapshot`
- Mechanism: `_userLockedAmounts[_user].tokenLocked = data[i].token;` is set for each snapshot with `lockAmount != 0`. If a user has snapshots locked in both USDB and WETH, the `tokenLocked` is overwritten to the last one processed, and `totalLockedAmount` sums both token amounts together regardless of token type.
- Impact: Mixed-token migrations are broken: the contract will try to lock the summed amount in the last-processed token, but the user only approved/transferred that one token. Reverts or fund misaccounting; users with mixed locks cannot migrate correctly.

## `MigrationManager.burnNFTs` Skips Purchased NFTs in Rarity Counting
- Location: `src/managers/MigrationManager.sol` : `burnNFTs`
- Mechanism: `burnNFTs` skips snapshots where `snapshot.lockAmount == 0` (purchased NFTs), so purchased NFTs are not burned here (they go through `burnRemainingPurchasedNFTs`). But the `_userLockedAction = LOCKED_BURN` is set unconditionally, preventing `LOCKED_FULL_MIGRATION` afterward. If a user has mixed locked + purchased NFTs and calls `burnNFTs` to burn locked ones, they're then forced into `LOCKED_BURN` and cannot migrate the purchased ones (must use `burnRemainingPurchasedNFTs`).
- Impact: Users can accidentally lock themselves out of migration by calling `burnNFTs` first; griefing via the authorization bypass above compounds this.

## `LockManager.unlock` Does Not Reset `unlockTime`/`lastLockTime`
- Location: `src/managers/LockManager.sol` : `unlock`
- Mechanism: `unlock` decrements `lockedToken.quantity` and transfers tokens but leaves `lockedToken.unlockTime`, `lastLockTime`, and `remainder` unchanged. If a user partially unlocks, the remaining `unlockTime` still reflects the original lock. If they fully unlock (`quantity` becomes 0), `unlockTime` and `lastLockTime` remain stale, and a subsequent `setLockDuration` will use the stale `lastLockTime` to compute a new `unlockTime`.
- Impact: Stale lock metadata can cause `setLockDuration` to compute incorrect `unlockTime` values (potentially in the past), and `getLockedWeightedValue` still counts `quantity > 0` only, so fully-unlocked tokens are OK — but partial unlocks with remainder semantics can be gamed.

## `LockManager._lock` Sets `unlockTime` Even Outside Lockdrop
- Location: `src/managers/LockManager.sol` : `_lock`
- Mechanism: `lockedToken.unlockTime = block.timestamp + _lockDuration;` is set unconditionally (inside the lockdrop block only NFTs are awarded, but the unlock time is set outside the lockdrop block too? Actually the `unlockTime` assignment is after the lockdrop block, so it always runs). If no lockdrop is configured (`lockdrop.start == 0`), the lockdrop block is skipped but locking still proceeds with `unlockTime = now + lockDuration`.
- Impact: Locking works outside lockdrop; `forceHarvest` is called, manipulating schnibble timing. May be intended, but combined with no lockdrop-active check, users can lock anytime to farm schnibbles/weighted value without NFT rewards.

## `ClaimManager.newPeriod` Does Not Validate `globalTotalChonk > 0`
- Location: `src/managers/ClaimManager.sol` : `newPeriod`, `_claimPoints`
- Mechanism: `currentPeriod.globalTotalChonk` is set in `newPeriod` to `snuggeryManager.getGlobalTotalChonk()`. In `_claimPoints`, if `globalTotalChonk == 0`, `claimAmount` is 0 for everyone, but if it's set to a stale value from the previous period and chonk changes between `newPeriod` and claims, the distribution is based on a snapshot that may be stale.
- Impact: Claim distribution uses a point-in-time global chonk snapshot; players who change their chonk after `newPeriod` but before claiming get unfair shares.

## `SnuggeryManager._recalculateChonks` Called After State Mutation
- Location: `src/managers/SnuggeryManager.sol` : `chonkUpdated` modifier
- Mechanism: The `chonkUpdated` modifier runs `forceClaimPoints(_player)` before the function body and `_recalculateChonks(_player)` after. But `forceClaimPoints` uses the current `totalGlobalChonk` and the player's current `playerChonks` (from `getTotalChonk`-style snapshot). If the function body changes the snuggery (import/export/feed), the points are claimed based on the pre-mutation chonk, then chonks are recalculated after. This is intended (claim-then-update), but `forceClaimPoints` reads `snuggeryManager.getTotalChonk(_player)` which iterates the current snuggery — which hasn't been mutated yet, so it reads the old value. However, `currentPeriod.globalTotalChonk` is the snapshot from `newPeriod`, not the live value. Discrepancy between live player chonk (used in claim) and snapshot global chonk (used as denominator) can cause `claimAmount > available`.
- Impact: If a player's live chonk exceeds their snapshot share, `claimAmount` can exceed the period's `available` (only capped by the global snapshot denominator, not the live one), inflating claims.

## `AccountManager.updatePlayer` Allows Full Player Overwrite
- Location: `src/managers/AccountManager.sol` : `updatePlayer`
- Mechanism: `updatePlayer` is callable by `SnuggeryManager` and `PrimordialManager`, and overwrites the entire `Player` struct: `players[_account] = _player;`. The caller can set arbitrary `registrationDate`, `referrer`, `lastHarvestDate`, `maxSnuggerySize`, `unfedSchnibbles`, etc. If either SnuggeryManager or PrimordialManager is compromised or has a bug, they can rewrite any player's data.
- Impact: A bug in SnuggeryManager/PrimordialManager (several noted above) can corrupt arbitrary player fields — e.g., set `unfedSchnibbles` to max, `lastHarvestDate` to future, `referrer` to attacker. High blast radius.

## `ConfigStorage` `setUintArray`/`setSmallUintArray`/etc. Don't Clean on Length-1 Edge
- Location: `src/config/ConfigStorage.sol` : `setUintArray`, `setSmallUintArray`, `setSmallIntArray`, `setAddressArray`
- Mechanism: The cleanup loop runs `for (j = uint8(arrLength); j < length[_key]; j++) delete ...`. If `arrLength == length[_key]`, no cleanup (OK). If `arrLength < length`, cleanup runs. But the length is stored as `uint8(arrLength)` — if `arrLength` exceeds 255 it's caught by the earlier check. However, the loop variable `j` is `uint8`, and if `length[_key]` is 255 and `arrLength` is 0, the loop `j = 0; j < 255` works. Edge: if `arrLength` is exactly 255, `uint8(arrLength) = 255`, and the cleanup loop `j = 255; j < 255` doesn't run — OK. No direct bug, but `getUintArray` uses `uint8 i` for the loop, capping reads at 255 — consistent.
- Impact: No direct exploit, but arrays are hard-capped at 255 with no length-1 edge issues. Not a vulnerability.

## `ConfigStorage.manualNotify` Index Arithmetic
- Location: `src/config/ConfigStorage.sol` : `manualNotify`
- Mechanism: `for (uint i = _index; i < _index + _length; i++)` with `_index` and `_length` as `uint8`. If `_index + _length` overflows `uint8`... but `i` is `uint256`, and `_index + _length` is computed in `uint8` then promoted? Actually `_index + _length` where both are `uint8` — Solidity promotes the sum to `uint8`? No, binary operations on `uint8` produce `uint8`, and overflow in 0.8 reverts. So `_index + _length` can revert if it exceeds 255. Then `i < _index + _length` uses the (possibly reverted) sum.
- Impact: `manualNotify` reverts if `_index + _length > 255`, limiting batch notify size; minor DoS.

## `AccountManager.getSubAccounts` Writes to Wrong Array Indices
- Location: `src/managers/AccountManager.sol` : `getSubAccounts`
- Mechanism: `for (i = _start; i < _start + MAX_SUB; i++) { if (i >= subAccountsLength) break; _subAccounts[i] = subAccounts[_player][i]; }`. The destination `_subAccounts` is sized `[20]`, but the index `i` starts at `_start`. If `_start > 0`, `_subAccounts[i]` writes beyond index 19 when `_start + MAX_SUB > 20`, causing out-of-bounds access (revert in 0.8).
- Impact: `getSubAccounts` with `_start > 0` reverts; pagination broken.

## Summary
The most severe issues are: permissionless `claimYieldForContracts` with arbitrary external calls, the `claimERC20Yield` wrong-token bug, the authorization bypass in `MigrationManager.burnNFTs`/`migrateAllNFTs` (anyone can burn/migrate another user's NFTs), `execSprayProposal`/`_tempSprayPlayerCheck` storage pollution and missing proposer validation, `convertPointsToTokens` inverted math, referral bonus not counted against `claimed`, `forceHarvest` griefing via NFT transfers, `getRole`/`onlyRole` per-contract context dependence, and the `SignatureVerifier` always-revert bug.
