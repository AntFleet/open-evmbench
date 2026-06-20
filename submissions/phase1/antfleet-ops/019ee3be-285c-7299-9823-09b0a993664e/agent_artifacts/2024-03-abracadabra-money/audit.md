# Audit: 2024-03-abracadabra-money

## Cap check after token transfer allows permanent fund loss on revert
- Location: src/blast/BlastOnboarding.sol : deposit
- Mechanism: `safeTransferFrom` executes unconditionally first, then `totals[token].total += amount` occurs, and only *after* that does the `if (caps[token] > 0 && totals[token].total > caps[token]) revert ErrCapReached();` check run. On revert the transfer has already succeeded but no entry exists in `balances[msg.sender][token]` or `totals`, leaving the tokens unaccounted for.
- Impact: Any user (or an attacker forcing the boundary) can send tokens that push the cap over the limit; the tokens remain permanently in the contract with no way for users to recover them (rescue is restricted to non-supported tokens and only callable by owner).

## Missing zero-length check in transferMultiple enables revert on empty arrays
- Location: src/DegenBox.sol : transferMultiple
- Mechanism: The function unconditionally executes `require(tos[0] != address(0), ...)` and then iterates `for (uint256 i = 0; i < len; i++)` where `len = tos.length`. When `tos.length == 0`, `tos[0]` reverts with an out-of-bounds panic before any balance updates.
- Impact: Any caller supplying empty `tos`/`shares` arrays (including legitimate batch callers or a griefing attempt) causes the transaction to revert, blocking all multi-transfers of that token regardless of approval status.

## Reward accounting can be front-run via multiple `notifyRewardAmount` calls within the same epoch
- Location: src/staking/LockingMultiRewards.sol : notifyRewardAmount
- Mechanism: The function reads `block.timestamp < reward.periodFinish`, adds the *remaining* reward amount to the new `amount`, then recomputes `rewardRate = amount / _remainingRewardTime`. There is no access-control or rate-limit on how many times an operator may call it inside the same `rewardsDuration` window; each call immediately overwrites `rewardRate` and `periodFinish`.
- Impact: A malicious or compromised operator can repeatedly call `notifyRewardAmount` with tiny amounts, inflating the apparent reward rate for the current epoch and thereby draining the entire reward balance into a single user's `earned` balance before honest stakers can react.

## `processExpiredLocks` can be called with stale `lastLockIndex` values, causing incorrect accounting
- Location: src/staking/LockingMultiRewards.sol : processExpiredLocks
- Mechanism: The function accepts an arbitrary `lockIndexes` array and only checks `if (index == lastLockIndex[user] && locks.length > 1) revert`. After swapping the last element into `locks[index]` it updates `lastLockIndex[user]` only when the removed index *was* the last one; otherwise `lastLockIndex[user]` can point to a now-invalid slot.
- Impact: Subsequent user operations (or another `processExpiredLocks` call) that rely on `lastLockIndex[user]` read a stale index, allowing a user to lock additional funds into an already-expired slot or causing `lock` to push the array past `maxLocks` without reverting.

## `sellShares` can be forced to return 0 shares when `totalSupply()==0` after the 1001 burn
- Location: src/mimswap/MagicLP.sol : sellShares
- Mechanism: When `totalSupply()==0` the `buyShares` path mints 1001 "dead" shares to `address(0)`. A subsequent `sellShares` call with any non-zero `shareAmount` will compute `baseAmount = (baseBalance * shareAmount) / 0`, reverting with division-by-zero (or, if the check were removed, returning 0).
- Impact: After the very first liquidity addition that leaves exactly the dead shares, any attempt to exit liquidity permanently bricks the pool for that token pair; attackers can front-run the initial deposit to force this state.
