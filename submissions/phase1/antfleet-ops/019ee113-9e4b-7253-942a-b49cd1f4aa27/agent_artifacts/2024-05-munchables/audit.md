# Audit: 2024-05-munchables

## Pet schnibbles calculation inflates balance by 1e18
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: The pet function distributes schnibbles to both petter and petted. `PET_TOTAL_SCHNIBBLES` and `bonusSchnibbles` are denominated in 1e18 (the config comment explicitly says `10e18 / 72`). The final split multiplies by an extra `1e18`:
  ```solidity
  uint256 petterSchnibbles = ((totalSchnibbles * 5) / 11) * 1e18;
  uint256 pettedSchnibbles = ((totalSchnibbles * 6) / 11) * 1e18;
  ```
  The trailing `* 1e18` is spurious — `totalSchnibbles` is already in 1e18 units, so the result is in 1e36. Every pet credits ~1e35 schnibbles to each party instead of ~0.07e18.
- Impact: Any player can inflate their `unfedSchnibbles` (and the petted player's) by ~1e18 per pet, which can then be fed into NFTs (minting chonks), used to claim points, or converted to MUNCH tokens in `ClaimManager.convertPointsToTokens`. Effectively a free-mint / inflation bug.

## RewardsManager claims WETH yield by calling USDB
- Location: `src/managers/RewardsManager.sol` : `_claimYieldForContract`
- Mechanism: The WETH branch passes `address(USDB)` to `claimERC20Yield` instead of `address(WETH)`:
  ```solidity
  if (_yieldWETH != 0) {
      IERC20YieldClaimable(_contract).claimERC20Yield(
          address(USDB),
          _yieldWETH
      );
  }
  ```
  The downstream `BaseBlastManager.claimERC20Yield` then calls `IERC20Rebasing(address(USDB)).claim(...)` with an amount that was measured against WETH's claimable balance. USDB has no such claimable balance, so the WETH yield is either never distributed or mis-accounted.
- Impact: WETH yield from yield-bearing contracts is permanently stuck or mis-credited. The protocol/treasury loses all WETH rebasing yield; accounting is broken.

## NFTOverlord `_populateDefaultRealmLookup` grows unbounded on every reconfigure
- Location: `src/overlords/NFTOverlord.sol` : `_populateDefaultRealmLookup` (called from `_reconfigure` / `configUpdated`)
- Mechanism: 
  ```solidity
  for (uint16 i = 0; i < realms.length; i++) {
      realmLookup.push(realms[i]);
  }
  ```
  `_reconfigure` is invoked every time the config storage changes. The function unconditionally pushes each entry to storage, never resetting the array. After N reconfigurations the array contains N copies of `RealmLookups`. `_createWithEntropy` indexes it with `realmLookup[speciesId]`; the first copy remains correct, but the array keeps growing.
- Impact: Unbounded state growth (eventually approaching the 24kB SSTORE2 ceiling) and gas-bound DoS in any function that touches the array. Each config update worsens it.

## Pagination view functions write out of bounds
- Location: `src/managers/SnuggeryManager.sol` : `getSnuggery` and `src/managers/AccountManager.sol` : `getSubAccounts`
- Mechanism: The returned array is allocated to a fixed size (`maxSize` capped at 10, or 20), but the loop writes at index `i = _start .. _start + maxSize - 1`:
  ```solidity
  _snuggery = new MunchablesCommonLib.SnuggeryNFT[](maxSize);
  for (uint256 i = _start; i < maxSize + _start; i++) {
      ...
      _snuggery[i].tokenId = snuggeryNFT.tokenId;  // OOB when i >= maxSize
  }
  ```
  Any non-zero `_start` causes out-of-bounds writes (Solidity 0.8 panics). The same pattern exists in `AccountManager.getSubAccounts` with `address[20]`.
- Impact: View functions revert on the first non-zero pagination call as soon as the player has more entries than the page size. Snuggery/UI cannot list large snuggeries or accounts with >5 sub-accounts at all.

## `getTotalChonk` silently truncates after 255 NFTs
- Location: `src/managers/SnuggeryManager.sol` : `getTotalChonk`
- Mechanism: The loop counter is declared as `uint8 i`:
  ```solidity
  for (uint8 i; i < snuggery.length; i++) {
      _totalChonk += nftAttributesManager.getAttributes(snuggery[i].tokenId).chonks;
  }
  ```
  The snuggery size is bounded by `maxSnuggerySize` (a `uint16`, up to 65535). When the player holds more than 255 NFTs, the loop stops iterating and `_totalChonk` only reflects the first 255.
- Impact: The value is used by `ClaimManager._claimPoints` to compute a player's share of the period's emission. Players with large snuggeries are silently under-paid for every chonk above the 255th, every period, forever.

## `migrateAllNFTs` lacks reentrancy guard
- Location: `src/managers/MigrationManager.sol` : `migrateAllNFTs`
- Mechanism: `migrateAllNFTs` is `external` with no `nonReentrant` (unlike `migratePurchasedNFTs` and `lockFundsForAllMigration`). It calls `_migrateNFTs`, which performs multiple external calls (`nftOverlord.mintForMigration`, `_oldNFTContract.burn`, `_lockManager.lockOnBehalf`). State mutations (`snapshot.claimed = true`, accounting, eventual `lockOnBehalf`) and the value-moving external call are interleaved. `LockManager.lockOnBehalf` does have a `nonReentrant`, but it can only stop the inner re-entry; any malicious or upgradeable callee that re-enters `MigrationManager` before the final `lockOnBehalf` runs in an unprotected context.
- Impact: A malicious or compromised callee (or a future upgrade to one of the trusted contracts) could re-enter `migrateAllNFTs` and double-process snapshots, mint extra NFTs, or otherwise break the migration accounting.

## USD oracle disapprovals are not cleared when the same oracle later approves
- Location: `src/managers/LockManager.sol` : `approveUSDPrice` and `disapproveUSDPrice`
- Mechanism: `disapproveUSDPrice` only writes `disapprovals[msg.sender] = _usdProposalId` and increments `disapprovalsCount`. `approveUSDPrice` writes `approvals[msg.sender] = _usdProposalId` and increments `approvalsCount` but does NOT decrement `disapprovalsCount` or clear the disapproval entry. An oracle that disapproves and then changes its mind still has its disapproval counted.
- Impact: A single oracle can both approve and disapprove the same proposal; the disapproval still counts toward `DISAPPROVE_THRESHOLD`. With threshold manipulation (3 of 5 oracles), a single swing voter can both "approve" and then "kill" a proposal by flipping back to disapproval (or vice versa), enabling griefing / price-update DoS.

## `SignatureVerifier.recover` rejects every signature
- Location: `src/libraries/SignatureVerifier.sol` : `recover`
- Mechanism: 
  ```solidity
  if (v != 27 || v != 28) revert InvalidSignature();
  ```
  The condition is always true (when `v == 27` the second clause `v != 28` is true), so every signature reverts. Additionally, the v extraction `byte(0, mload(add(signature, 96)))` reads the most-significant byte of a 32-byte right-aligned word, which is always `0` for a valid ABI-encoded `uint8 v`; it should be `byte(31, ...)`.
- Impact: The library is unusable as written — `ecrecover` is never reached. While the audited code does not call it today, any future EOA-signed message path (e.g. off-chain reveals, oracle attestations) that imports this library will be permanently bricked. The latent bug should be fixed before it is wired in.
