# Audit: 2024-07-munchables

# Audit Report

## 1. Unconditional `_lastClaimPeriod` Update Causes Reward Loss

- **Location:** `ClaimManager.sol` : `_claimPoints`
- **Mechanism:** The line `_lastClaimPeriod[_player] = currentPeriodId;` is executed unconditionally at the end of the function, even when `claimAmount == 0` (e.g., the player has no chonks). Because `forceClaimPoints` is called from the `chonkUpdated` modifier *before* import/feed/export actions complete, a player importing their first munchable will have `forceClaimPoints` called when they have zero chonks. The period claim is consumed (marked as claimed) but zero points are awarded. The player can never claim for that period again.
- **Impact:** Players lose an entire period's worth of reward points whenever `forceClaimPoints` is triggered while they temporarily have zero chonks (e.g., first import, after exporting all munchables, or when `globalTotalChonk` is zero at period start).

## 2. Unvalidated Referrer Enables Self-Referral Bonus Farming

- **Location:** `AccountManager.sol` : `register`
- **Mechanism:** The `register` function only checks `_referrer == msg.sender` (self-referral) but does not verify that `_referrer` is a registered player. An attacker can register with `_referrer = addressTheyControl` (unregistered). When the attacker claims points, `ClaimManager._claimPoints` credits referral bonus points to `_points[referrer]` regardless of whether the referrer is registered. The attacker then registers the referrer address and claims the accumulated referral bonus.
- **Impact:** An attacker can farm referral bonuses by setting self-controlled addresses as referrers, extracting extra reward tokens beyond their legitimate share.

## 3. `rescue` Uses `transferFrom` Instead of `transfer` for ERC20

- **Location:** `MigrationManager.sol` : `rescue`
- **Mechanism:** The `rescue` function calls `IERC20(_tokenContract).transferFrom(address(this), _returnAddress, _quantity)`. `transferFrom` requires the spender (msg.sender / admin) to have allowance from `address(this)`. The contract never approves itself or the admin, so this call will always revert due to insufficient allowance. It should use `transfer` instead.
- **Impact:** Admin cannot rescue stuck ERC20 tokens from the MigrationManager contract. Any ERC20 tokens accidentally sent to or remaining in the contract are permanently locked.

## 4. Off-by-One in Plot Validity Check During Farming

- **Location:** `LandManager.sol` : `_farmPlots`
- **Mechanism:** The condition `if (_getNumPlots(landlord) < _toiler.plotId)` should be `<=`. Plot IDs are 0-indexed and valid range is `0` to `totalPlots - 1` (enforced in `stakeMunchable` with `plotId >= totalPlotsAvail`). When `_getNumPlots(landlord) == _toiler.plotId`, the plot is out of bounds, but the condition evaluates to false, so the munchable continues farming in an invalid plot instead of being marked dirty and frozen at the last update time.
- **Impact:** Munchables staked in plots that become invalid (due to landlord reducing locked tokens) continue to accrue schnibbles based on `block.timestamp` instead of being frozen, giving the renter unfair rewards.

## 5. Incorrect Bonus Math in Farm Plot Schnibble Calculation

- **Location:** `LandManager.sol` : `_farmPlots`
- **Mechanism:** The bonus formula is `uint256((int256(schnibblesTotal) + (int256(schnibblesTotal) * finalBonus)) / 100)`. This computes `schnibblesTotal * (1 + finalBonus) / 100`. If `finalBonus` represents a percentage (e.g., 10 for 10%), the result is `schnibblesTotal * 11 / 100 = 0.11 * base`, which is an 89% reduction, not a 10% bonus. The correct formula should be `schnibblesTotal + (schnibblesTotal * finalBonus / 100)` or `schnibblesTotal * (100 + finalBonus) / 100`. Additionally, `finalBonus` is unclamped here (unlike in `BonusManager.getFeedBonus`), so large negative values can cause the `uint256()` cast to revert, blocking farming for all renters on that plot.
- **Impact:** Farming rewards are drastically miscalculated (reduced by ~90% if bonuses are percentage-scale), or transactions revert entirely if bonus values are sufficiently negative, locking renters out of farming.

## 6. `getSubAccounts` Returns Misaligned Array

- **Location:** `AccountManager.sol` : `getSubAccounts`
- **Mechanism:** The loop writes to `_subAccounts[i]` where `i` starts at `_start`, but the returned array is always `[20]` indexed from 0. When `_start > 0`, entries `0` to `_start-1` are zero, and only indices `_start` through `_start+19` (or fewer) are populated. The correct index should be `_subAccounts[i - _start]`.
- **Impact:** Frontend and any on-chain consumers receive a mostly-empty array with data at wrong offsets, breaking sub-account pagination and potentially causing UI to display incorrect data or miss sub-accounts.

## 7. Duplicate Token IDs in `migratePurchasedNFTs` Cause ETH Overcharge

- **Location:** `MigrationManager.sol` : `migratePurchasedNFTs`
- **Mechanism:** The outer loop in `migratePurchasedNFTs` counts `quantity += purchasedUnlockPrice` for every unclaimed tokenId, including duplicates in the `tokenIds` array. The inner `_migrateNFTs` sets `snapshot.claimed = true` on first encounter and `continue`s on subsequent duplicates, so only one `purchasedUnlockPrice` is forwarded to LockManager. The user's `msg.value` check `(quantity * discountFactor) / 10e12` uses the inflated outer `quantity`, so the user overpays. The excess ETH is stuck in the contract.
- **Impact:** Users who include duplicate token IDs in the array lose ETH (difference between paid and locked amounts) with no way to recover it except admin `rescue`.

## 8. Storage Key Reuse — `PrimordialsEnabled` Used for Both Boolean and Address

- **Location:** `AccountManager.sol` : `_reconfigure` and `updatePlayer`; `PrimordialManager.sol` : `_reconfigure`
- **Mechanism:** `AccountManager._reconfigure` loads `landManager` from `configStorage.getAddress(StorageKey.PrimordialsEnabled)`, treating the same key as an address. `PrimordialManager._reconfigure` loads `primordialsEnabled = configStorage.getBool(StorageKey.PrimordialsEnabled)`, treating the same key as a boolean. While these read from different underlying mappings (`addressStorage` vs `boolStorage`), the admin must set both independently for the same enum key. If the admin sets only the address (to configure LandManager), `getBool` returns false (default), disabling primordials. If the admin sets only the boolean, `getAddress` returns zero, breaking LandManager access control in `updatePlayer`.
- **Impact:** Misconfiguration can either disable primordial claiming entirely or break LandManager's ability to update player metadata, depending on which value the admin sets.

## 9. `pet` Function — Extraneous `* 1e18` Multiplication

- **Location:** `SnuggeryManager.sol` : `pet`
- **Mechanism:** The lines `petterSchnibbles = ((totalSchnibbles * 5) / 11) * 1e18` and `pettedSchnibbles = ((totalSchnibbles * 6) / 11) * 1e18` include an extra `* 1e18`. If `PET_TOTAL_SCHNIBBLES` is stored in 1e18 units (as the comment `10e18 / 72` suggests), this produces astronomically large values (on the order of 1e34), inflating pet rewards by a factor of ~1e18. Additionally, the sum `petterSchnibbles + pettedSchnibbles` does not equal `totalSchnibbles` due to rounding, causing a small reward leak per pet.
- **Impact:** If `PET_TOTAL_SCHNIBBLES` is configured in 1e18 units (per the code comment), petting rewards are inflated by ~1e18×, allowing attackers to drain the reward system exponentially faster than intended.

## 10. Missing Reentrancy Guard on Permissionless Yield Claiming

- **Location:** `RewardsManager.sol` : `claimYieldForContracts` / `_claimYieldForContract`
- **Mechanism:** `claimYieldForContracts` is callable by anyone with arbitrary `_contracts` addresses. For each contract, `_claimYieldForContract` calls `IERC20YieldClaimable(_contract).claimERC20Yield(...)` — an external call to a user-supplied address. A malicious contract can reenter `claimYieldForContracts` or other RewardsManager functions during this callback. While `getClaimableAmount` is read before the callback, the actual `claim` on Blast may return a different amount if yield was already claimed in a reentrant call, causing `ongoingUSDB`/`ongoingWETH` to be inflated relative to actual tokens received. The subsequent `_forwardYield` then approves/forwards amounts that may not exist.
- **Impact:** A malicious contract in the `_contracts` array can cause accounting mismatches between expected and actual yield, potentially leading to failed transfers or inconsistent state in the yield distribution pipeline.

## 11. `FundTreasuryDistributor.receiveTokens` — Multiple ETH Entries Cause Revert

- **Location:** `FundTreasuryDistributor.sol` : `receiveTokens`
- **Mechanism:** For ETH transfers (`tokenContract == address(0)`), the check `if (msg.value != amount) revert InvalidMsgValueError()` compares `msg.value` (the total ETH sent in the transaction) against the individual `amount` for each `TokenBag` entry. If the `tb` array contains two or more ETH entries, `msg.value` equals the sum of all ETH amounts, which will not match any individual `amount`, causing a revert.
- **Impact:** Any call distributing multiple ETH token bags in a single transaction will always fail, breaking batch ETH distribution.
