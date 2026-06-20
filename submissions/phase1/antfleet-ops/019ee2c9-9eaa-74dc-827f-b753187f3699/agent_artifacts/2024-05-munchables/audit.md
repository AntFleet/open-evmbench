# Audit: 2024-05-munchables

## Petting mints `1e18`-inflated schnibbles
- Location: `src/managers/SnuggeryManager.sol : pet`
- Mechanism: `PET_TOTAL_SCHNIBBLES` is already stored in 18-decimal units, but `pet()` computes each side’s payout as `((totalSchnibbles * 5) / 11) * 1e18` and `((totalSchnibbles * 6) / 11) * 1e18`. That final `* 1e18` scales an already-scaled value a second time, so every pet action credits balances roughly `1e18` times larger than intended.
- Impact: Any two cooperating players can print astronomically large `unfedSchnibbles` every cooldown cycle, then feed NFTs and compound into the rest of the reward system.

## Lock-based pet bonuses can be claimed without locking anything
- Location: `src/managers/LockManager.sol : setLockDuration`, `src/managers/BonusManager.sol : getPetBonus`, `src/managers/SnuggeryManager.sol : pet`
- Mechanism: `setLockDuration()` lets any user store an arbitrary lock duration up to `MaxLockDuration` even when they have no locked position. `getPetBonus()` then derives the pet bonus solely from that stored duration and never checks that the caller currently has any locked value. `pet()` trusts that bonus directly.
- Impact: An attacker can set the maximum duration for free and farm the full “locked-user” pet bonus with zero capital at risk.

## Migration bonus formula explodes near the upper threshold
- Location: `src/managers/BonusManager.sol : _calculateMigrationBonus`
- Mechanism: The linear interpolation branch uses `(migrationBonus * (weightedValue - halfAmount)) / (migrateHighestAmount - weightedValue)`. The denominator is wrong: it shrinks toward zero as `weightedValue` approaches `migrateHighestAmount`, so the returned bonus grows far beyond the configured `migrationBonus` instead of smoothly approaching it.
- Impact: A migrator can choose a position just below the top threshold and receive an arbitrarily oversized harvest bonus, letting them mint far more schnibbles than intended during the migration-bonus window.

## Expired locks still earn full “locked” rewards
- Location: `src/managers/LockManager.sol : getLockedWeightedValue`
- Mechanism: `getLockedWeightedValue()` counts `lockedTokens[_player][token].quantity` whenever the token is active, but it never checks whether `unlockTime` has already passed. That stale value feeds both `AccountManager.getDailySchnibbles()` and the bonus calculations, so tokens remain reward-bearing after they are fully unlockable.
- Impact: Users can wait until the lock expires, keep the assets withdrawable on demand, and still accrue the same emissions as if the position were genuinely locked, defeating the protocol’s lockup economics.

## WETH yield claims are routed to the USDB claim path
- Location: `src/managers/RewardsManager.sol : _claimYieldForContract`
- Mechanism: In the WETH branch, the code calls `IERC20YieldClaimable(_contract).claimERC20Yield(address(USDB), _yieldWETH)` instead of passing `address(WETH)`. As a result, WETH yield is never actually claimed from the managed contract, but `_forwardYield()` still assumes that WETH was collected and tries to forward it.
- Impact: WETH yield can become permanently stuck, and a claim batch that includes positive WETH yield can revert during forwarding because the `RewardsManager` does not actually hold the promised WETH balance.

