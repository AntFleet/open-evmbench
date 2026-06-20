# Audit: 2024-05-munchables

## Snapshot owner can burn or migrate sold NFTs
- Location: `src/managers/MigrationManager.sol` : `burnNFTs`, `burnRemainingPurchasedNFTs`, `migrateAllNFTs`, `migratePurchasedNFTs`
- Mechanism: Migration authorization is based only on the snapshot owner/key. The code never checks the current `OldMunchNFT.ownerOf(tokenId)` before calling `_oldNFTContract.burn(tokenId)`, and `OldMunchNFT.burn` trusts `MigrationManager`.
- Impact: A snapshot owner can sell or transfer an old NFT, then later burn/migrate it anyway, destroying the buyer’s NFT and receiving the new NFT or points themselves.

## Anyone can extend another user’s token lock with a zero-value lock
- Location: `src/managers/LockManager.sol` : `lockOnBehalf` / `_lock`
- Mechanism: `lockOnBehalf` is public and accepts `_quantity == 0`. `_lock` still updates `lastLockTime` and `unlockTime` for `_lockRecipient` even when no tokens are transferred.
- Impact: An attacker can repeatedly call `lockOnBehalf(token, 0, victim)` to push a victim’s `unlockTime` forward indefinitely, griefing withdrawals of already locked funds.

## Lock duration can be shortened to unlock early
- Location: `src/managers/LockManager.sol` : `setLockDuration`
- Mechanism: The reduction check compares `block.timestamp + _duration` against the old `unlockTime`, but the assignment sets `unlockTime = lastLockTime + _duration`. After enough time has elapsed, a shorter duration passes the check while setting `unlockTime` into the past.
- Impact: A locker can receive long-duration benefits, then reduce the effective lock and withdraw before the originally committed unlock time.

## ERC20 locks credit amounts that were not received
- Location: `src/managers/LockManager.sol` : `_lock`, `unlock`
- Mechanism: ERC20 `transferFrom` and `transfer` return values are ignored, and the contract does not verify balance deltas. Fee-on-transfer or false-returning configured tokens can cause the contract to credit the full `_quantity` while receiving less or nothing.
- Impact: A user can receive inflated locked balance, NFT reveals, and harvest weight without depositing equivalent collateral, potentially draining pooled token balances on unlock.

## Pet rewards are multiplied by `1e18` twice
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: `PET_TOTAL_SCHNIBBLES` is already configured as an 18-decimal amount, but `petterSchnibbles` and `pettedSchnibbles` multiply the split result by another `1e18`.
- Impact: Any two accounts can pet on cooldown to mint astronomically inflated unfed schnibbles, then feed/claim through the rest of the economy.

## Migration bonus formula can explode near the cap
- Location: `src/managers/BonusManager.sol` : `_calculateMigrationBonus`
- Mechanism: The linear interpolation divides by `(migrateHighestAmount - weightedValue)` instead of the fixed range `(migrateHighestAmount - halfAmount)`. As `weightedValue` approaches `migrateHighestAmount`, the denominator approaches zero.
- Impact: A migrated user can tune locked value just below the upper threshold and receive an excessive harvest bonus, inflating schnibble generation.

## Snuggery bonus changes are applied retroactively
- Location: `src/managers/SnuggeryManager.sol` : `importMunchable`, `exportMunchable`, `feed`
- Mechanism: These functions mutate snuggery contents/chonks/levels, which affect `BonusManager.getHarvestBonus`, without first forcing `AccountManager` harvest. The next harvest computes the new bonus over all elapsed time since the previous harvest.
- Impact: A user can import or boost NFTs immediately before harvesting and receive bonus schnibbles as if those NFTs or levels had been present for the whole accrual period.

## Munchadex transfer harvesting uses post-transfer state
- Location: `src/managers/MunchadexManager.sol` : `updateMunchadex`
- Mechanism: The contract updates Munchadex counters before calling `accountManager.forceHarvest`. The receiver harvests with the newly gained Munchadex bonus retroactively applied to prior elapsed time.
- Impact: An attacker can move collection NFTs to a high-lock account just before harvest to claim unearned bonus schnibbles for the previous accrual interval.

## WETH yield claims use the USDB token address
- Location: `src/managers/RewardsManager.sol` : `_claimYieldForContract`
- Mechanism: The WETH branch calculates `_yieldWETH`, but calls `claimERC20Yield(address(USDB), _yieldWETH)` instead of `address(WETH)`. The later forwarding path then assumes WETH was received.
- Impact: Any nonzero WETH yield can make yield claiming revert or leave WETH unclaimed, blocking distribution of protocol yield for affected contracts.

