# Audit: 2024-05-munchables

## Snapshot owner can steal migrated NFTs after sale
- Location: `src/managers/MigrationManager.sol` : `_migrateNFTs`, `burnNFTs`, `burnRemainingPurchasedNFTs`
- Mechanism: Migration actions trust the snapshot owner `_user` and never verify that `_user` still owns the old NFT at execution time before calling `_oldNFTContract.burn(tokenId)`. `OldMunchNFT.burn` also does not check ownership because it trusts `MigrationManager`.
- Impact: A snapshot owner can sell/transfer an old NFT, then later burn the buyer’s NFT and either mint the migrated NFT to themselves or claim burn points.

## Petting mints schnibbles with an extra 1e18 multiplier
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: `PET_TOTAL_SCHNIBBLES` is already treated as a scaled schnibbles amount, but `petterSchnibbles` and `pettedSchnibbles` multiply by `1e18` again: `((totalSchnibbles * 5) / 11) * 1e18`.
- Impact: Attackers can repeatedly pet between accounts to mint astronomically inflated unfed schnibbles, then feed NFTs, dominate chonk totals, and drain points/token emissions.

## Migration bonus can become unbounded near the full-bonus threshold
- Location: `src/managers/BonusManager.sol` : `_calculateMigrationBonus`
- Mechanism: The partial migration bonus divides by `(migrateHighestAmount - weightedValue)` instead of the fixed range `(migrateHighestAmount - halfAmount)`. As `weightedValue` approaches `migrateHighestAmount`, the denominator approaches zero and the computed bonus explodes.
- Impact: A migrated user can tune their locked value just below the full-bonus threshold to receive an enormous harvest multiplier and inflate schnibbles, chonks, and downstream point rewards.

## Lock duration can be shortened below the original unlock time
- Location: `src/managers/LockManager.sol` : `setLockDuration`
- Mechanism: The reduction check compares `block.timestamp + _duration` against the current `unlockTime`, but then sets the new unlock time to `lastLockTime + _duration`. After enough time has elapsed, this allows a duration that passes the check while setting `unlockTime` much earlier than the existing unlock.
- Impact: Users can commit to a long lock to receive long-lock benefits, then shorten the actual lock and withdraw funds earlier than intended.

## WETH yield is claimed using the USDB token address
- Location: `src/managers/RewardsManager.sol` : `_claimYieldForContract`
- Mechanism: When WETH yield is detected, the code calls `claimERC20Yield(address(USDB), _yieldWETH)` instead of using `address(WETH)`. The accounting then assumes WETH was claimed even though the WETH yield remains unclaimed.
- Impact: WETH yield claims can revert during forwarding or leave WETH yield permanently stuck; if the rewards manager holds unrelated WETH, that balance can be forwarded while the actual claimable WETH remains behind.

## Configured fee-on-transfer or false-return ERC20s inflate lock accounting
- Location: `src/managers/LockManager.sol` : `_lock`
- Mechanism: ERC20 locks credit `lockedToken.quantity += _quantity` and mint reveal entitlement from `_quantity` before verifying the actual token amount received. The code also ignores the boolean return value of `transferFrom`.
- Impact: If an active configured token is fee-on-transfer or returns `false` without transferring, users can receive inflated locked balances, weighted value, and NFT reveal credit without depositing the full amount.

