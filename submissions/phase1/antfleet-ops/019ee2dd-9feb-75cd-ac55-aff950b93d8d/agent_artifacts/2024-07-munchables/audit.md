# Audit: 2024-07-munchables

 ## LandManager loads game parameters from contract-address StorageKeys
- Location: `src/managers/LandManager.sol` : `_reconfigure()`
- Mechanism: `MIN_TAX_RATE`, `MAX_TAX_RATE`, `DEFAULT_TAX_RATE`, `BASE_SCHNIBBLE_RATE`, and `PRICE_PER_PLOT` are read with `getUint` from `StorageKey.LockManager`, `StorageKey.AccountManager`, `StorageKey.ClaimManager`, `StorageKey.MigrationManager`, and `StorageKey.NFTOverlord`. Those keys store contract addresses, not numeric configuration values, so all of the LandManager’s economic parameters become the casted addresses of other protocol contracts.
- Impact: Tax-rate bounds, base schnibble yield, and plot price are uncontrollable and determined by deployment addresses. `updateTaxRate` and plot calculations operate on garbage values; `PRICE_PER_PLOT` is almost certainly so large that `_getNumPlots` returns 0 for every user, rendering staking and farming unusable.

## AccountManager references LandManager through a boolean StorageKey
- Location: `src/managers/AccountManager.sol` : `_reconfigure()`
- Mechanism: `landManager` is set from `configStorage.getAddress(StorageKey.PrimordialsEnabled)`. That key is a boolean config entry, not an address entry, so unless the owner also writes an address into the separate `addressStorage` mapping for that enum, `landManager` resolves to the zero address.
- Impact: Every call to `LockManager.lock`, `LockManager.unlock`, and `LockManager.setLockDuration` triggers `AccountManager.forceHarvest`, which in turn calls `landManager.updatePlotMetadata(_player)` when the caller is the LockManager. With `landManager == address(0)`, those core locking operations always revert, bricking user funds.

## `SnuggeryManager.pet` inflates schnibble rewards by 1e18
- Location: `src/managers/SnuggeryManager.sol` : `pet()`
- Mechanism: The function computes `totalSchnibbles` from `PET_TOTAL_SCHNIBBLES` (already in wei scale, e.g. `10e18 / 72`) and a bonus, then multiplies the split shares by `1e18` again: `((totalSchnibbles * 5) / 11) * 1e18`.
- Impact: Each pet action mints roughly 10^18 times the intended schnibbles to both players. This allows unbounded inflation of `unfedSchnibbles`, instantly max-leveling Munchables and breaking the in-game economy.

## `LandManager._farmPlots` underflows to huge rewards on negative bonuses
- Location: `src/managers/LandManager.sol` : `_farmPlots()`
- Mechanism: `schnibblesTotal` is converted to `int256`, multiplied by `finalBonus` (the sum of configurable realm and rarity bonuses), divided by 100, and then cast back to `uint256`. If the admin or a compromised oracle sets a sufficiently negative realm bonus, the intermediate value becomes negative; the explicit `uint256` cast turns it into a number near `type(uint256).max`.
- Impact: A farmer can earn effectively infinite `unfedSchnibbles` and landlord schnibbles in a single transaction by farming a Munchable whose combined bonus is below -100.

## `MigrationManager.rescue` cannot withdraw ERC20 tokens
- Location: `src/managers/MigrationManager.sol` : `rescue()`
- Mechanism: For non-ETH rescues the function calls `IERC20(_tokenContract).transferFrom(address(this), _returnAddress, _quantity)` instead of `transfer`. OpenZeppelin-style `transferFrom` consumes allowance even when the spender equals the owner, and the MigrationManager never approves itself, so the call reverts due to insufficient allowance.
- Impact: Admin rescue of ERC20 tokens sent to the contract by mistake will always fail, permanently freezing those funds. The ETH path also uses `.send`, which can fail for contract recipients.

## RewardsManager yield/gas claims are unpermissioned
- Location: `src/managers/RewardsManager.sol` : `claimYieldForContracts()`, `claimGasFeeForContracts()`
- Mechanism: Both functions have no access-control modifier, so any external caller can invoke Blast yield/gas claims for arbitrary contract lists and forward the proceeds to the configured distributors.
- Impact: While funds are sent to protocol-controlled distributors, anyone can force claims at unfavorable gas prices or trigger yield events, enabling gas griefing and removing the intended administrative/keeper control over claim timing.

## `ConfigStorage.notify` unbounded loop can block config updates
- Location: `src/config/ConfigStorage.sol` : `notify()`, `addNotifiableAddress()`, all owner setters with `_notify == true`
- Mechanism: `notify()` iterates over the entire `notifiableAddresses` array and makes external calls. There is no cap on the array length, and a malicious or simply buggy registered notifiable contract can revert or consume excessive gas.
- Impact: A single bad notifiable address (added by owner or via compromise) can make every configuration setter that uses `_notify=true` run out of gas or revert, freezing protocol-wide configuration updates until manual `removeNotifiableAddress` succeeds.

## `AccountManager.rewardSpray` cap reads the wrong configuration key
- Location: `src/managers/AccountManager.sol` : `_reconfigure()`, `rewardSpray()`
- Mechanism: `maxRewardSpray` is loaded from `configStorage.getUint(StorageKey.MinETHPetBonus)` instead of a dedicated spray cap. The comment in `_reconfigure()` explicitly marks `MinETHPetBonus` as an “artifact, unused.”
- Impact: The per-player reward spray limit is controlled by an unrelated, deprecated config value, so the cap may be orders of magnitude too high or effectively zero, allowing the `NFTOracle` reward EOA to over- or under-allocate schnibbles at will.

## `PrimordialManager.hatchPrimordialToMunchable` ignores the primordials-enabled flag
- Location: `src/managers/PrimordialManager.sol` : `hatchPrimordialToMunchable()`
- Mechanism: `claimPrimordial()` and `feedPrimordial()` are guarded by `onlyPrimordialsEnabled`, but `hatchPrimordialToMunchable()` only checks `notPaused`.
- Impact: If primordials are disabled via config after players have already claimed/raised one, those players can still hatch their primordials into Munchables, bypassing the intended global shutdown.

## `MunchNFT._update` does not prevent transfers to blacklisted accounts
- Location: `src/tokens/MunchNFT.sol` : `_update()`
- Mechanism: The transfer hook reverts only when the sender (`from`) or the token is blacklisted; it never checks whether the recipient (`_to`) is blacklisted.
- Impact: A blacklisted account can still receive MunchNFTs, defeating the purpose of the account blacklist and allowing sanctioned tokens/accounts to accumulate or launder NFTs.

## `LockManager.getLockedWeightedValue` underflows for tokens with more than 18 decimals
- Location: `src/managers/LockManager.sol` : `getLockedWeightedValue()`
- Mechanism: The function computes `10 ** (18 - configuredToken.decimals)`. If a configured token has more than 18 decimals, the subtraction underflows to a huge number, producing a wildly inflated locked value.
- Impact: A high-decimal token configured by the admin makes a user’s weighted lock value enormous, granting disproportionate harvests, plots, and rewards. Combined with `configureToken` lacking a decimals sanity check, this is an admin-configurable exploit path.

## `ConfigStorage.setAddresses` loop counter can wrap on long inputs
- Location: `src/config/ConfigStorage.sol` : `setAddresses()`
- Mechanism: The loop variable `i` is declared as `uint8`, but `_keys.length` is not bounded. If the owner supplies more than 255 key/value pairs, `i` wraps back to zero and the loop runs until out of gas.
- Impact: A legitimate but oversized batched config update becomes a permanent DoS for that function call.
