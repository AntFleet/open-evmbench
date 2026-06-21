# Audit: 2024-05-munchables

## Lock duration check uses wrong timestamp reference
- Location: `src/managers/LockManager.sol` : `setLockDuration`
- Mechanism: When a player updates their lock duration, the anti-shortening guard compares `block.timestamp + _duration` against the existing `unlockTime`, but the new `unlockTime` is written as `lastLockTime + _duration`. Because `lastLockTime` is the time of the original lock (always ≤ `block.timestamp`), the stored unlock time can be far earlier than the value the guard evaluated. A player can pick a new duration that passes the check yet sets `unlockTime` to a timestamp already in the past.
- Impact: A player can shorten or eliminate their lock period and call `unlock` to withdraw ETH/ERC20 immediately, while `playerSettings.lockDuration` still reflects the longer duration used for harvest/pet bonuses. Locked funds belonging to the protocol’s lockdrop can be withdrawn early.

## Referral bonuses bypass period emission cap
- Location: `src/managers/ClaimManager.sol` : `_claimPoints`
- Mechanism: Period point distribution is supposed to be bounded by `currentPeriod.available + _pointsExcess[currentPeriodId]`. The player’s pro-rata `claimAmount` is added to `currentPeriod.claimed`, but the referrer’s `_referralBonus` is credited to `_points[player.referrer]` without incrementing `currentPeriod.claimed` or checking remaining supply. The TODO comment in-code acknowledges this omission.
- Impact: An attacker operating a referrer account and many referred sub-accounts can farm chonk and repeatedly claim, minting referral bonus points that are never counted against the period budget. Those excess points can be spent or converted to `$MUNCH` via `convertPointsToTokens`, diluting honest users and exceeding intended emissions.

## Migration bonus division by near-zero denominator
- Location: `src/managers/BonusManager.sol` : `_calculateMigrationBonus`
- Mechanism: For migrated users whose `weightedValue` falls between `halfAmount` and `migrateHighestAmount`, the bonus is computed as `(migrationBonus * (weightedValue - halfAmount)) / (migrateHighestAmount - weightedValue)`. As `weightedValue` approaches `migrateHighestAmount`, the denominator tends toward zero, producing arbitrarily large bonus values before the `weightedValue >= migrateHighestAmount` branch is taken.
- Impact: A migrator can lock a carefully chosen amount so `getLockedWeightedValue` sits just below `migrateHighestAmount`, receive an outsized `getHarvestBonus`, and accrue far more schnibbles than intended through `harvest`/`forceHarvest`, extracting excess in-game value.

## Migration contract pools user deposits without per-user accounting
- Location: `src/managers/MigrationManager.sol` : `lockFundsForAllMigration`, `_migrateNFTs`, `migratePurchasedNFTs`
- Mechanism: ETH and ERC20 paid into `lockFundsForAllMigration` sit in the `MigrationManager` contract balance with no per-user escrow ledger. Later, `_migrateNFTs` funds `lockOnBehalf` via `lockOnBehalf{value: quantity}` or `WETH.approve` / `USDB.approve` from the contract’s pooled balance. Any caller whose migration executes while the pool holds other users’ funds will have their `lockOnBehalf` call funded from the shared balance, not from an isolated deposit.
- Impact: A user who calls `migratePurchasedNFTs` or `migrateAllNFTs` after another user has deposited migration funds can have their lock paid from the victim’s deposit. The victim’s later migration can revert for insufficient balance, effectively stealing locked migration collateral and griefing or blocking honest migrators.

## WETH yield claimed against USDB token address
- Location: `src/managers/RewardsManager.sol` : `_claimYieldForContract`
- Mechanism: When claiming WETH yield, the code reads `getClaimableAmount` for WETH correctly, but the subsequent `claimERC20Yield` call passes `address(USDB)` as the token parameter instead of `address(WETH)`. WETH rebasing yield is therefore claimed through the wrong token interface.
- Impact: WETH yield for managed contracts is not claimed correctly—calls may revert (DoS on yield harvesting) or, depending on token implementation, claim the wrong asset—causing loss of WETH yield that should be forwarded to the treasury distributor.

## Lock remainder wiped outside lockdrop window
- Location: `src/managers/LockManager.sol` : `_lock`
- Mechanism: During an active lockdrop, partial deposits toward the next NFT are stored in `lockedToken.remainder`. Outside the lockdrop window, the NFT-remainder logic is skipped, leaving the local `remainder` variable at its default of `0`, and `lockedToken.remainder = remainder` unconditionally overwrites any previously accumulated remainder.
- Impact: A user who locked during the lockdrop and accumulates a non-zero remainder loses that credit if they add to their lock after the lockdrop ends. They must deposit more than `nftCost` to earn the next unrevealed NFT, causing loss of earned lockdrop entitlement.

## ECDSA recovery guard always reverts
- Location: `src/libraries/SignatureVerifier.sol` : `recover`
- Mechanism: The signature-version check reads `if (v != 27 || v != 28) revert InvalidSignature()`. Because `v` cannot simultaneously equal 27 and 28, at least one side of the `||` is always true for any value of `v`, so the condition is always satisfied and the function always reverts before `ecrecover` runs. The intended logic almost certainly used `&&`.
- Impact: Any code path that relies on `SignatureVerifier.recover` (e.g., oracle/RNG signature validation referenced by `InvalidOracleError` in the interfaces) will reject all valid signatures, causing a permanent DoS of signed operations—or, if the check were ever “fixed” inconsistently elsewhere, inconsistent validation behavior.

