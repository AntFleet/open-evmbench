# Audit: 2024-05-munchables

## Early unlock via `setLockDuration` measuring from `lastLockTime` instead of now
- Location: src/managers/LockManager.sol : setLockDuration
- Mechanism: The reduce-time guard compares `block.timestamp + _duration` against the stored `unlockTime`, but the new unlock time is then written as `lastLockTime + _duration`. Because `lastLockTime <= block.timestamp`, a caller can pick a `_duration` that satisfies the guard (`now + _duration >= unlockTime`) while producing `lastLockTime + _duration <= now`. Concretely, once roughly half the original lock has elapsed (`now - lastLockTime >= oldDuration/2`), choosing `_duration` in the range `[oldDuration - elapsed, elapsed]` passes the check yet sets `unlockTime` to a value in the past, after which `unlock()` succeeds immediately.
- Impact: A user can collapse their remaining lock and withdraw locked tokens early while keeping the NFTs that were minted to them for the original lock commitment, extracting the lockdrop reward without honoring the lock.

## Migration harvest bonus divides by `(migrateHighestAmount - weightedValue)`, exploding the bonus
- Location: src/managers/BonusManager.sol : _calculateMigrationBonus
- Mechanism: In the middle branch the bonus is `(migrationBonus * (weightedValue - halfAmount)) / (migrateHighestAmount - weightedValue)`. The denominator shrinks toward zero as the player's `weightedValue` (their current locked weighted USD value, which they control by locking) approaches `migrateHighestAmount`, so the result grows without bound. A migrated user (within `migrationBonusEndTime`) can tune their locked quantity so `weightedValue` sits just below `migrateHighestAmount`, yielding an astronomically large bonus. `getHarvestBonus` returns this unclamped, and `_harvest` applies `dailySchnibbles += dailySchnibbles * bonus / 1e18`.
- Impact: An attacker mints essentially unlimited schnibbles per harvest, which feed into chonks, period point claims, and ultimately MUNCH token minting, breaking the entire reward economy.

## `lockOnBehalf` lets anyone perpetually extend a victim's unlock time
- Location: src/managers/LockManager.sol : lockOnBehalf (_lock)
- Mechanism: `lockOnBehalf` lets any caller lock an arbitrary `_quantity` (down to 1 wei) crediting `_onBehalfOf`, and `_lock` unconditionally sets `lockedTokens[_lockRecipient][...].unlockTime = block.timestamp + _lockDuration` using the *recipient's* `lockDuration`, plus resets `lastLockTime = block.timestamp`. There is no consent check and no requirement that the new unlock time exceed the old. An attacker repeatedly dust-locks on behalf of a registered victim, each time pushing `unlockTime` back to `now + victimDuration`; because `lastLockTime` is also reset, the victim cannot use the `setLockDuration` path to shorten it either.
- Impact: An attacker can grief any user by keeping their locked tokens permanently non-withdrawable for the cost of dust plus gas.

## Claim accounting lets `claimed` exceed `available`, bricking `newPeriod`
- Location: src/managers/ClaimManager.sol : _claimPoints / newPeriod
- Mechanism: `_claimPoints` distributes `availablePoints = currentPeriod.available + _pointsExcess[currentPeriodId]` weighted by the caller's *live* `getTotalChonk` over the *stale* period-start `globalTotalChonk`, and adds each result to `currentPeriod.claimed`. Since the rolled-over excess inflates the numerator while `claimed` is only ever reconciled against `available`, the sum of claims can reach `available + excess > available` (and live-vs-snapshot chonk growth makes shares sum to more than 1, worsening it). The next `newPeriod` then executes `uint256 _excess = currentPeriod.available - currentPeriod.claimed`, which underflows and reverts.
- Impact: Players can claim more points than the period emits, and once `claimed` exceeds `available` the period rollover reverts permanently, freezing all future point claims (denial of service on the core points system).

## WETH yield is claimed from the USDB token in `_claimYieldForContract`
- Location: src/managers/RewardsManager.sol : _claimYieldForContract
- Mechanism: The WETH branch reads `_yieldWETH = IERC20Rebasing(WETH).getClaimableAmount(_contract)` but then calls `IERC20YieldClaimable(_contract).claimERC20Yield(address(USDB), _yieldWETH)` — it passes `address(USDB)` instead of `address(WETH)`. The target therefore claims `_yieldWETH` of USDB rather than the WETH yield, while `_forwardYield` still builds and `approve`s a WETH bag for `ongoingWETH` that the contract never actually received.
- Impact: WETH yield is never collected and USDB is over-claimed by the WETH amount; the subsequent WETH transfer to the distributor underflows the manager's balance and reverts, so yield claiming breaks for any contract accruing WETH yield.

## `pet` double-scales schnibble rewards by an extra 1e18
- Location: src/managers/SnuggeryManager.sol : pet
- Mechanism: `PET_TOTAL_SCHNIBBLES` is configured in 1e18 units (per the `// 10e18 / 72` reconfigure comment), yet `petterSchnibbles`/`pettedSchnibbles` are computed as `((totalSchnibbles * 5) / 11) * 1e18` and `((totalSchnibbles * 6) / 11) * 1e18`, multiplying an already-1e18-scaled value by `1e18` again. Instead of the intended ~5e18 / 6e18 schnibbles per pet, the function credits ~1e34-scale amounts.
- Impact: Each pet mints orders-of-magnitude more schnibbles than intended to both petter and petted, which convert into chonks, claimable points, and MUNCH tokens, allowing reward inflation.

## `approveUSDPrice` does not block oracles that already disapproved
- Location: src/managers/LockManager.sol : approveUSDPrice
- Mechanism: `approveUSDPrice` only rejects a duplicate when `usdUpdateProposal.approvals[msg.sender] == _usdProposalId`; it never checks `disapprovals[msg.sender]`. The symmetric `disapproveUSDPrice` does reject prior approvers, so an oracle can call `disapproveUSDPrice` (incrementing `disapprovalsCount`) and then `approveUSDPrice` (incrementing `approvalsCount`) for the same proposal, counting toward both thresholds with a single identity.
- Impact: A price-feed oracle can vote on both sides of the same proposal, corrupting the approval/disapproval quorum that gates oracle price updates and undermining the multi-oracle integrity of `getLockedWeightedValue` pricing.

