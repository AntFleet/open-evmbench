# Audit: 2024-05-munchables

## Griefing Lock Extension via `lockOnBehalf`
- Location: `LockManager.sol` : `lockOnBehalf` / `_lock`
- Mechanism: The `lockOnBehalf` helper allows any user to lock tokens on behalf of another address (`_onBehalfOf`). The internal function `_lock` recalculates the recipient's unlock time using their currently stored `lockDuration` from `playerSettings` (or defaults to `lockdrop.minLockDuration` if set to 0), and updates it to `uint32(block.timestamp) + uint32(_lockDuration)`. Because there is no check verifying that the caller of `lockOnBehalf` is authorized by the recipient, any caller can lock a minimal amount of tokens (e.g., 1 wei) on behalf of any registered user.
- Impact: An attacker can repeatedly call `lockOnBehalf` with a dust amount of tokens to perpetually extend a victim's unlock time to a future date, effectively freezing their locked assets indefinitely and preventing them from ever withdrawing.

## Munchadex State Desynchronization via `safeTransferFrom`
- Location: `MunchNFT.sol` : `transferFrom` / `_update`
- Mechanism: The `MunchNFT.sol` contract overrides the `transferFrom` function of `ERC721` to sync ownership changes with the `MunchadexManager` but does not override `safeTransferFrom` or perform this logic in the internal `_update` hook. In OpenZeppelin's `ERC721` standard, calling `safeTransferFrom` bypasses the public calling of `transferFrom` and directly operates through internal methods. Therefore, transferring a Munchable NFT using `safeTransferFrom` completely bypasses the Munchadex update.
- Impact: Users can transfer their Munchables using `safeTransferFrom` while leaving their Munchadex stats unchanged. This enables users to copy and retain Munchadex harvest bonuses across multiple wallets, inflating reward accruals. Additionally, when a subsequent handler attempts to transfer the NFT away using standard `transferFrom` or on a typical marketplace, the unique species decrement operation in `updateMunchadex` will panic underflow because the recipient's species count was never initiated, permanently locking the NFT from such transfers.

## Arbitrary Point Inflation via Dynamic Player Chonks vs. Snapshotted Global Chonks
- Location: `ClaimManager.sol` : `_claimPoints`
- Mechanism: In `_claimPoints()`, a player's claimable points are computed as `(snuggeryManager.getTotalChonk(_player) * availablePoints) / currentPeriod.globalTotalChonk`. While the denominator `currentPeriod.globalTotalChonk` is snapshotted once at the initiation of the period in `newPeriod()`, the numerator `getTotalChonk(_player)` is dynamically fetched at the exact moment of claiming.
- Impact: A player can hoard unfed schnibbles, wait for a new period to start (setting a low snapshotted `globalTotalChonk`), feed their Munchables to inflate their `totalChonk`, and then claim points. This mismatch allows players to generate and claim a disproportionately large share of available points (potentially exceeding 100% of the period's available emission), leading to severe inflation of reward points.

## Retroactive Harvest Bonus Manipulation via Snuggery Changes (Import/Export/Feed)
- Location: `SnuggeryManager.sol` : `importMunchable`, `exportMunchable`, `feed`
- Mechanism: The level bonus of Munchables in a player's snuggery is recalculated dynamically inside `_calculateLevelBonus` during reward harvesting. While lock and unlock actions in `LockManager` correctly call `forceHarvest` beforehand to capture and lock rewards accrued at the old rate, importing, exporting, or feeding Munchables (which alters snuggery size and Levels) directly updates snuggery composition without triggering a harvest.
- Impact: Users can manipulate their level bonuses retroactively for elapsed periods. For example, a user can import a high-level Munchable into their snuggery seconds before harvesting, receiving retroactively boosted rewards for the entire duration since their last harvest. Conversely, honest users who export a Munchable before harvesting will face a retroactive reduction in their accrued rewards.

## Retroactive Harvest Bonus Calculation using Post-Update Munchadex State
- Location: `MunchadexManager.sol` : `updateMunchadex`
- Mechanism: In `updateMunchadex`, `accountManager.forceHarvest` is invoked to secure pending rewards for both the sender and the receiver of an NFT. However, this invocation occurs at the end of the `if` blocks *after* the `munchadex` state (species counts and unique species count) has already been updated. When `_harvest` is processed, it evaluates the user's harvest rate based on the *new* Munchadex state instead of the *old* state active during the accrual period.
- Impact: The sender of an NFT is retroactively penalized and loses accrued rewards since their last harvest because the lower post-transfer Munchadex bonus is applied. Meanwhile, the receiver gets an exploit window where they receive secondary accrued rewards at the higher rate retroactively, leading to unfair reward payouts.

## Denial of Service via `.transfer` to Treasury and Recipient Contracts
- Location: `FundTreasuryDistributor.sol` : `receiveTokens` and `LockManager.sol` : `unlock`
- Mechanism: The `receiveTokens` and `unlock` functions transfer native ETH to the `_treasury` or `msg.sender` address using the Solidity `.transfer(...)` method. The `.transfer` method has a hardcoded gas limit of 2300 gas.
- Impact: If the configured treasury address or the locking participant is a smart contract wallet (such as a standard Gnosis Safe multisig or an account abstraction wallet), executing native token transfers will run out of gas and revert. This results in a complete Denial of Service (DoS) for yield collection, native token lockups distribution, and locked ETH withdrawals.

## Overfeeding Level 0 Primordials of Valuable Schnibbles
- Location: `PrimordialManager.sol` : `feedPrimordial`
- Mechanism: Inside `feedPrimordial`, the overfeeding protection that adjusts the consumed `_schnibbles` and caps attributes to level thresholds is wrapped inside the condition `if (currentLevel < 0)`. Once a primordial reaches level 0, this block is bypassed entirely during future feeding transactions.
- Impact: When the primordial is already at level 0, players can still select to feed it valuable schnibbles. The contract will subtract an unlimited amount of schnibbles from the user's profile and increment `chonks` with no level-up benefits or refunds, permanently destroying the user's valuable schnibbles.
