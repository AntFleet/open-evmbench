# Audit: 2024-07-munchables

# Security Audit Findings

## Broken pagination in `getSubAccounts` causes OOB write and revert
- Location: `src/managers/AccountManager.sol` : `getSubAccounts`
- Mechanism: The function declares a fixed-size memory array `address[20] memory _subAccounts` and then iterates with `for (uint256 i = _start; i < _start + MAX_SUB; i++) { _subAccounts[i] = ... }`. When `_start > 0` the index `i` reaches 20, writing to `_subAccounts[20]` which is out of bounds for the 20-element array. Solidity 0.8.x traps this with `Panic(0x22)`, so any call with `_start >= 1` reverts unconditionally. The intended pagination is completely unusable beyond page 0.
- Impact: Front-ends and any caller cannot retrieve sub-accounts beyond the first 20; the function is effectively a DoS for any non-zero `_start`. The state itself is unchanged (view function), but the contract's documented pagination interface is broken.

## Pet reward calculation has a spurious `* 1e18` scaling
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: 
  ```solidity
  uint256 bonusSchnibbles = (PET_TOTAL_SCHNIBBLES * bonusPercent) / 1e18;
  uint256 totalSchnibbles = PET_TOTAL_SCHNIBBLES + uint256(bonusSchnibbles);
  uint256 petterSchnibbles = ((totalSchnibbles * 5) / 11) * 1e18;
  uint256 pettedSchnibbles = ((totalSchnibbles * 6) / 11) * 1e18;
  ```
  The trailing `* 1e18` multiplies the already-computed share by 10^18. `totalSchnibbles` is already in the same unit basis as `unfedSchnibbles` (e.g. `PET_TOTAL_SCHNIBBLES` is added directly to `unfedSchnibbles` via `accountManager.updatePlayer`). The `* 1e18` therefore inflates the pet reward by a factor of 10^18.
- Impact: Every pet action credits the petter and petted with ~1e18× the intended schnibble amount. Combined with the 10-minute cooldown, a coordinated pair of accounts can drain points/bonuses from the global economy and inflate individual `unfedSchnibbles` balances by astronomical amounts.

## LandManager wires its numeric constants to contract-address StorageKeys
- Location: `src/managers/LandManager.sol` : `_reconfigure`
- Mechanism:
  ```solidity
  MIN_TAX_RATE      = IConfigStorage(configStorage).getUint(StorageKey.LockManager);
  MAX_TAX_RATE      = IConfigStorage(configStorage).getUint(StorageKey.AccountManager);
  DEFAULT_TAX_RATE  = IConfigStorage(configStorage).getUint(StorageKey.ClaimManager);
  BASE_SCHNIBBLE_RATE = IConfigStorage(configStorage).getUint(StorageKey.MigrationManager);
  PRICE_PER_PLOT    = IConfigStorage(configStorage).getUint(StorageKey.NFTOverlord);
  ```
  These `StorageKey` enum values are used elsewhere for contract addresses stored in `addressStorage`. `getUint` reads from `uintStorage`, which is never written to for these keys, so every constant resolves to `0`.
- Impact: `PRICE_PER_PLOT == 0` causes `_getNumPlots` to divide by zero and revert in `stakeMunchable` / `transferToUnoccupiedPlot` / `_farmPlots`. `BASE_SCHNIBBLE_RATE == 0` makes `_farmPlots` always distribute zero schnibbles. `MIN_TAX_RATE == MAX_TAX_RATE == 0` makes any non-zero tax rate revert in `updateTaxRate`, while a zero tax rate is meaningless. The entire land/farming subsystem is non-functional after a normal reconfigure.

## `MigrationManager.rescue` uses `transferFrom` to send its own tokens
- Location: `src/managers/MigrationManager.sol` : `rescue`
- Mechanism: The contract holds user-locked ERC20s (from `lockFundsForAllMigration` and `_migrateNFTs`). The rescue function does `IERC20(_tokenContract).transferFrom(address(this), _returnAddress, _quantity)`, which requires the caller to be approved by `address(this)`. A contract cannot approve itself, and the caller here is the same contract, so the allowance is always 0.
- Impact: Admin token rescue is permanently broken; depending on the token's `transferFrom` implementation this either silently no-ops (non-reverting tokens) or reverts (reverting tokens), preventing the admin from recovering stuck funds in an incident.

## `MunchNFT._update` does not block transfers whose `to` is blacklisted
- Location: `src/tokens/MunchNFT.sol` : `_update`
- Mechanism: The blacklist guard only inspects the sender:
  ```solidity
  if (_blacklistAccount[from] || _blacklistToken[_tokenId]) revert ForbiddenTransferError();
  ```
  The recipient address is never checked, and `mint` also has no blacklist check on the recipient.
- Impact: An admin can blacklist an account to stop its outbound transfers, but anyone can still airdrop or push NFTs into that account (or mint a fresh NFT directly to it via `NFTOverlord`). Combined with the fact that a blacklisted `from` cannot send, NFTs deposited this way become permanently stuck in the blacklisted account, and the blacklist mechanism gives a false sense of containment.

## `MunchNFT._update` performs the external `munchadexManager.updateMunchadex` call before blacklist/state checks
- Location: `src/tokens/MunchNFT.sol` : `_update`
- Mechanism: `updateMunchadex` (an external call) runs before the blacklist check and before `super._update`. On a blacklisted transfer the function reverts, but the side effects inside `MunchadexManager.updateMunchadex` (decrementing counters, decrementing `numUnique`, calling `accountManager.forceHarvest`) have already executed in the same transaction. More importantly, the external call is performed while the ERC721 invariants are still in their pre-transfer state.
- Impact: Gas is wasted on every blacklisted-revert path, and the ordering makes the function fragile against any future reentrancy from `MunchadexManager`/`AccountManager` (e.g. via `forceHarvest` -> harvest -> external hook). Not directly exploitable today, but it is the kind of pattern that becomes a vulnerability the moment one of those callees is upgraded to perform untrusted external calls.

## `ClaimManager._claimPoints` credits referral bonus to an unregistered referrer
- Location: `src/managers/ClaimManager.sol` : `_claimPoints`
- Mechanism:
  ```solidity
  if (player.referrer != address(0)) {
      _referralBonus = (claimAmount * bonusManager.getReferralBonus()) / 1e18;
      _points[player.referrer] += _referralBonus;
  }
  ```
  `AccountManager.register` does not validate that `_referrer` is a registered player, so the referrer can be any EOA/contract. Points are written into `_points[player.referrer]` regardless of registration status.
- Impact: If the referrer is a contract that cannot call `claimPoints`/`convertPointsToTokens` (or an EOA that never registers), the bonus is permanently locked. Because `getPoints` looks the address up through `accountManager.getMainAccount` which returns the input for unregistered addresses, an unregistered referrer's points can never be spent or converted. There is no admin path to recover them.

## `ConfigStorage.manualNotify` silently no-ops on out-of-range input
- Location: `src/config/ConfigStorage.sol` : `manualNotify`
- Mechanism: The loop is `for (uint i = _index; i < _index + _length; i++) { if (i >= notifiableAddresses.length) break; ... }`. Any `_index`/`_length` pair that starts past the end (or is otherwise invalid) silently does nothing instead of reverting.
- Impact: An owner calling `manualNotify` with bad indices will believe they re-notified contracts when nothing happened. The lack of validation makes operational mistakes around config propagation hard to detect.

## `AccountManager.register` does not validate the referrer
- Location: `src/managers/AccountManager.sol` : `register`
- Mechanism: `register` accepts any `_referrer` address, including the zero address, the player's own address (`SelfReferralError` catches self-referral), unregistered EOAs, and contracts. Combined with `spraySchnibblesPropose`/`rewardSpray` writing `unclaimedSchnibbles[player]` which is then claimed on registration, a player can register with a referrer they control and route future referral bonuses to themselves indirectly.
- Impact: Referral rewards can be siphoned to attacker-controlled addresses (and ultimately back to the attacker). Also enables griefing where a victim is set as someone else's referrer without their consent, misattributing the on-chain relationship.
