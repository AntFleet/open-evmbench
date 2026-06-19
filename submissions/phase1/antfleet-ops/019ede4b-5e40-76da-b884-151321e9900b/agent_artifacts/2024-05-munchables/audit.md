# Audit: 2024-05-munchables

## 1. Signature Verification Logic Flaw (Always Reverts)
- Location: `src/libraries/SignatureVerifier.sol` : `recover`
- Mechanism: The validation check for the signature version uses a logical OR instead of AND: `if (v != 27 || v != 28) revert InvalidSignature();`. Since `v` cannot simultaneously be 27 and 28, one of the inequalities will always evaluate to true. This causes the function to unconditionally revert for every valid signature.
- Impact: Any contract or feature relying on this library for signature verification (e.g., off-chain oracle signatures) will be permanently broken and unusable.

## 2. Critical Accounting Flaw in Migration Allows ETH Drain
- Location: `src/managers/MigrationManager.sol` : `lockFundsForAllMigration` & `migrateAllNFTs`
- Mechanism: `lockFundsForAllMigration` only requires the user to send ETH for their `totalLockAmount` (locked NFTs), completely ignoring `totalPurchaseAmount` (purchased NFTs). However, `migrateAllNFTs` processes ALL NFTs and calls `_lockManager.lockOnBehalf{value: quantity}` where `quantity` includes both locked and purchased amounts. If the `MigrationManager` contract holds a surplus of ETH from other users' locked funds, it will use that surplus to pay for the attacker's purchased NFTs.
- Impact: An attacker with both locked and purchased NFTs can underpay during the locking phase and drain the contract's ETH balance to cover the cost of their purchased NFTs, stealing funds deposited by other users.

## 3. Migration Bonus Calculation Denominator Error
- Location: `src/managers/BonusManager.sol` : `_calculateMigrationBonus`
- Mechanism: The linear interpolation formula for the migration bonus uses `(migrateHighestAmount - weightedValue)` as the denominator instead of the correct `(migrateHighestAmount - halfAmount)`. As a user's `weightedValue` approaches `migrateHighestAmount`, the denominator approaches zero, causing the calculated bonus to skyrocket towards infinity.
- Impact: Users can obtain an astronomically high harvest bonus by locking an amount just slightly below the maximum threshold, allowing them to farm excessive schnibbles and break the point/token economy.

## 4. Munchadex Bypass via safeTransferFrom
- Location: `src/tokens/MunchNFT.sol` : `transferFrom`
- Mechanism: The contract overrides `transferFrom` to call `munchadexManager.updateMunchadex` to track NFT ownership for bonus calculations, but fails to override `safeTransferFrom`. Users can simply use `safeTransferFrom` to transfer NFTs without triggering the update hook.
- Impact: Users can bypass the Munchadex tracking system, allowing them to retain Munchadex bonuses after selling/transferring NFTs, or fail to gain bonuses when receiving them, breaking the game's economic and bonus mechanics.

## 5. Incorrect Token Address in WETH Yield Claim
- Location: `src/managers/RewardsManager.sol` : `_claimYieldForContract`
- Mechanism: When claiming WETH yield, the code mistakenly passes `address(USDB)` to `claimERC20Yield` instead of `address(WETH)`: `IERC20YieldClaimable(_contract).claimERC20Yield(address(USDB), _yieldWETH);`. This is a copy-paste error from the USDB claim block above it.
- Impact: WETH yield cannot be claimed correctly. Depending on the target contract's implementation, it will either revert (causing a DoS on yield claiming for that contract) or incorrectly drain USDB yield instead of WETH yield.

## 6. RNG Request Index Collision
- Location: `src/overlords/NFTOverlord.sol` : `mintFromPrimordial` & `startReveal`
- Mechanism: `mintFromPrimordial` uses `uint256(uint160(_player))` as the RNG request index. `startReveal` uses `uint256(uint160(_mainAccount)) | (uint256(revealNonce) << 160)`. If a user calls `startReveal` when their `revealNonce` is 0 (their first reveal), the resulting index is identical to the primordial index. Since `BaseRNGProxy.requests` maps the index to request data, the second request will overwrite the first.
- Impact: A user can intentionally or accidentally overwrite their pending RNG requests, causing one of the callbacks to never execute or execute the wrong callback, permanently locking their reveal queue or primordial hatch.

## 7. Pagination Out-of-Bounds Revert in getSnuggery
- Location: `src/managers/SnuggeryManager.sol` : `getSnuggery`
- Mechanism: The function allocates `_snuggery` with a max size of 10 but indexes it using the loop variable `i` (which starts at `_start`). If a user paginates and `_start >= 10`, the code attempts to write to `_snuggery[i]`, which is out of bounds for the allocated array, causing a panic revert.
- Impact: Denial of Service for frontends and users trying to view snugeries with more than 10 NFTs when paginating.

## 8. Pagination Out-of-Bounds Revert in getSubAccounts
- Location: `src/managers/AccountManager.sol` : `getSubAccounts`
- Mechanism: Similar to the snuggery bug, the function allocates a fixed-size array `address[20] memory _subAccounts` but uses the loop variable `i` (starting at `_start`) to index into it (`_subAccounts[i] = ...`). If `_start >= 20`, it will attempt to write out of bounds and revert.
- Impact: Denial of Service for users and frontends attempting to paginate sub-accounts beyond the first page.
