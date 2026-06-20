# Audit: 2024-05-munchables

 ## [CRITICAL] Pet rewards inflated by an extra 1e18 factor
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: After computing `totalSchnibbles = PET_TOTAL_SCHNIBBLES + bonusSchnibbles`, the reward splits are calculated as `((totalSchnibbles * 5) / 11) * 1e18` and `((totalSchnibbles * 6) / 11) * 1e18`. Because `PET_TOTAL_SCHNIBBLES` is already a schnibble amount with 18 decimals, multiplying the split by another `1e18` inflates every pet payout by `10^18`.
- Impact: Any user can generate astronomically large `unfedSchnibbles` balances per `pet()` call, allowing instant level-ups, massive chonk inflation, and distortion of the points/yield economy.

## [CRITICAL] Harvest (and locking/unlocking) DoS for accounts with more than 10 Munchables
- Location: `src/managers/BonusManager.sol` : `_calculateLevelBonus` (reached via `getHarvestBonus` → `getDailySchnibbles` → `_harvest`, and via `forceHarvest` in `LockManager.unlock`/`MunchadexManager.updateMunchadex`)
- Mechanism: `_calculateLevelBonus` calls `accountManager.getFullPlayerData(_caller)`, which calls `snuggeryManager.getSnuggery(..., 0)`. `getSnuggery` returns a `_snuggery` array capped at 10 entries but returns the real `_snuggerySize`. The bonus loop then iterates `i < _snuggerySize` and reads `_snuggery[i]`; once a player owns more than 10 NFTs this reads past the array end and reverts.
- Impact: Players with >10 Munchables cannot harvest schnibbles, cannot claim points (because `forceClaimPoints` also depends on chonk/bonus reads), and may be unable to lock/unlock or transfer NFTs because those flows call `forceHarvest`. Locked funds can become permanently stuck.

## [CRITICAL] RewardsManager claims WETH yield using the USDB token contract
- Location: `src/managers/RewardsManager.sol` : `_claimYieldForContract`
- Mechanism: When processing WETH yield the code calls `IERC20YieldClaimable(_contract).claimERC20Yield(address(USDB), _yieldWETH)` instead of `address(WETH)`. The target contract's `claimERC20Yield` therefore executes `USDB.claim(RewardsManager, _yieldWETH)`.
- Impact: WETH yield is never collected; USDB yield is over-claimed by the WETH amount. If the contract’s claimable USDB balance is insufficient the whole yield claim reverts, and if sufficient the contract accumulates/stuck USDB while WETH yield remains unclaimed, breaking yield accounting.

## [HIGH] Migration harvest bonus grows unbounded near the cap
- Location: `src/managers/BonusManager.sol` : `_calculateMigrationBonus`
- Mechanism: The migration bonus is computed as `(migrationBonus * (weightedValue - halfAmount)) / (migrateHighestAmount - weightedValue)`. The denominator shrinks to zero as `weightedValue` approaches `migrateHighestAmount` (twice the original migrated locked USD value), so a user who locks just below that threshold receives an arbitrarily large harvest bonus.
- Impact: A migrating user can lock capital slightly below the migration-bonus cap and obtain a disproportionately huge harvest multiplier, generating outsized schnibbles and distorting reward distribution.

## [MEDIUM] RewardsManager yield/gas claim functions lack access control
- Location: `src/managers/RewardsManager.sol` : `claimYieldForContracts`, `claimGasFeeForContracts`
- Mechanism: Both functions are declared `external` with no role or ownership modifier, so any address can invoke them.
- Impact: Anyone can force the protocol to sweep Blast yield/gas for arbitrary contracts and forward the proceeds to the configured distributors, enabling unauthorized triggering and amplification of issues such as the WETH/USDB mis-claim.

## [MEDIUM] `getLockedWeightedValue` reverts for tokens with more than 18 decimals
- Location: `src/managers/LockManager.sol` : `configureToken` / `getLockedWeightedValue`
- Mechanism: `configureToken` does not validate `decimals`, but `getLockedWeightedValue` computes `10 ** (18 - decimals)`. For any configured token whose `decimals` exceeds 18 the subtraction underflows and reverts.
- Impact: All harvest calculations and weighted-value reads fail for users who locked that token, breaking schnibble accrual and any global flow that relies on the weighted value.

## [MEDIUM] `ConfigStorage.setAddresses` has an unbounded `uint8` loop
- Location: `src/config/ConfigStorage.sol` : `setAddresses`
- Mechanism: The loop `for (uint8 i; i < _keys.length; i++)` has no upper bound on `_keys.length`. If the owner supplies arrays longer than 255, `i` wraps back to 0 and the loop never terminates. The function also never verifies `_keys.length == _values.length`.
- Impact: An oversized or mismatched owner call runs out of gas or writes config values using wrong addresses, breaking the central configuration store.

## [MEDIUM] `SnuggeryManager.getTotalChonk` uses a `uint8` loop over unbounded snuggery size
- Location: `src/managers/SnuggeryManager.sol` : `getTotalChonk`
- Mechanism: `for (uint8 i; i < snuggery.length; i++)` iterates with a `uint8` counter. If a player expands their snuggery beyond 255 NFTs, the counter wraps and the loop never terminates.
- Impact: `forceClaimPoints` and other callers of `getTotalChonk` revert for such players, blocking point claims and chonk-dependent operations.

## [LOW] `SignatureVerifier.recover` rejects every valid signature
- Location: `src/libraries/SignatureVerifier.sol` : `recover`
- Mechanism: The check `if (v != 27 || v != 28) revert InvalidSignature();` is a tautology because `v` cannot equal both 27 and 28 simultaneously. The intended logic should use `&&`.
- Impact: Any signature-verification flow that relies on this library will permanently revert, causing denial of service for ECDSA-dependent functionality.

## [LOW] `ConfigStorage.manualNotify` index/length `uint8` overflow
- Location: `src/config/ConfigStorage.sol` : `manualNotify`
- Mechanism: `_index` and `_length` are `uint8`, and the loop bound `_index + _length` is evaluated in `uint8`, overflowing when the sum exceeds 255.
- Impact: The owner cannot use `manualNotify` to notify contracts past the 255 boundary, limiting recovery/notification of large notifiable-address lists.

## [LOW] `ConfigStorage.notify` has an unbounded gas loop
- Location: `src/config/ConfigStorage.sol` : `notify`
- Mechanism: `notify()` iterates over the entire `notifiableAddresses` array without pagination or cap. Every setter called with `_notify=true` executes this loop.
- Impact: As the owner adds notifiable contracts, config updates that trigger notification eventually exceed the block gas limit and revert, freezing those configuration changes until addresses are removed.

## [LOW] `SnuggeryManager.getSnuggery` pagination writes out of bounds
- Location: `src/managers/SnuggeryManager.sol` : `getSnuggery`
- Mechanism: The function allocates the returned `_snuggery` array with size `maxSize` (capped at 10) but loops while `i < maxSize + _start`. For any `_start > 0` the loop writes past the end of the returned array.
- Impact: Any external view call with a non-zero start index reverts, breaking pagination for UI integrations.

## [LOW] `SnuggeryManager.importMunchable` approval check is inverted
- Location: `src/managers/SnuggeryManager.sol` : `importMunchable`
- Mechanism: The check `erc721Token.getApproved(_tokenId) != address(this)` succeeds when there is no approval or when approval is set to any address other than the SnuggeryManager, and fails when approval is specifically set to the SnuggeryManager. The intended logic should be `== address(this)`.
- Impact: Users cannot import a Munchable using a single-token `approve`; only `setApprovalForAll` works, breaking the intended import flow.
