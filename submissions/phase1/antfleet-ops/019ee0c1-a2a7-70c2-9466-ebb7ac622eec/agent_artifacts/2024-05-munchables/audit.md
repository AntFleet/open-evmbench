# Audit: 2024-05-munchables

I found these genuine security vulnerabilities:

## Lock duration can be shortened retroactively
- Location: `src/managers/LockManager.sol` : `setLockDuration`
- Mechanism: The anti-reduction check compares `block.timestamp + _duration` against the current `unlockTime`, but the stored value is updated to `lastLockTime + _duration`. After time has elapsed, a user can choose `_duration = oldUnlockTime - block.timestamp`, pass the check, and set `unlockTime` much earlier than before, often into the past.
- Impact: A locker can withdraw tokens before the intended lock duration while keeping rewards/NFT benefits earned from the lock.

## Unlocked remainder can be reused to mint undercollateralized NFTs
- Location: `src/managers/LockManager.sol` : `_lock`, `unlock`
- Mechanism: During lockdrop, NFT entitlement is calculated from `_quantity + lockedToken.remainder`, but `unlock()` reduces only `lockedToken.quantity` and never reduces or clears `lockedToken.remainder`. A user can lock less than `nftCost`, accumulate a remainder, unlock the underlying tokens, then later lock only the missing dust amount and have the stale remainder count again.
- Impact: Attackers can mint reveal entitlements without maintaining the full required locked amount.

## ERC20 transfers are not verified
- Location: `src/managers/LockManager.sol` : `_lock`, `unlock`; `src/managers/MigrationManager.sol` : `lockFundsForAllMigration`, `_migrateNFTs`; `src/distributors/FundTreasuryDistributor.sol` : `receiveTokens`
- Mechanism: The code calls `transfer`/`transferFrom` without checking the returned boolean and records the requested `_quantity` instead of the actual balance delta. Fee-on-transfer tokens or ERC20s that return `false` can therefore be treated as successfully deposited or distributed.
- Impact: If such a token is configured, users can receive inflated lock credit, NFT reveals, schnibble rewards, or migration credit without the contract receiving the full assets; later withdrawals can drain other users’ token balances.

## Munchadex bonuses apply retroactively on NFT transfer
- Location: `src/managers/MunchadexManager.sol` : `updateMunchadex`
- Mechanism: The Munchadex counters are mutated before `accountManager.forceHarvest()` is called. On inbound transfers, the recipient is harvested after receiving the new Munchadex bonus, so the higher bonus is applied to the entire elapsed period since their last harvest. On outbound transfers, the sender can avoid the symmetric loss by harvesting just before transferring out.
- Impact: A collection can be rotated across accounts to retroactively boost harvest rewards for multiple locked accounts, minting excess schnibbles.

## Pet rewards are scaled by 1e18 twice
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: `PET_TOTAL_SCHNIBBLES` is loaded as an already 1e18-scaled schnibble amount, but `pet()` multiplies the derived petter and petted rewards by `1e18` again. This credits rewards many orders of magnitude larger than configured.
- Impact: Attackers can repeatedly pet and mint enormous unfed schnibble balances, then feed NFTs and inflate downstream chonk/points rewards.

## Migration harvest bonus can explode near the cap
- Location: `src/managers/BonusManager.sol` : `_calculateMigrationBonus`
- Mechanism: The linear interpolation denominator is `migrateHighestAmount - weightedValue` instead of the fixed interval size between `halfAmount` and `migrateHighestAmount`. As `weightedValue` approaches `migrateHighestAmount` from below, the denominator approaches zero and the returned bonus becomes arbitrarily large.
- Impact: Migrated users can receive a massively inflated harvest bonus and mint far more schnibbles than intended.

## WETH yield is claimed as USDB
- Location: `src/managers/RewardsManager.sol` : `_claimYieldForContract`
- Mechanism: After reading WETH claimable yield, the contract calls `claimERC20Yield(address(USDB), _yieldWETH)` instead of using `address(WETH)`. The accounting then adds `_yieldWETH` to the WETH token bag even though WETH was never claimed.
- Impact: WETH yield remains unclaimed, and yield forwarding can revert or distribute incorrect assets, causing WETH rewards to be stuck and yield collection to fail for affected contracts.

