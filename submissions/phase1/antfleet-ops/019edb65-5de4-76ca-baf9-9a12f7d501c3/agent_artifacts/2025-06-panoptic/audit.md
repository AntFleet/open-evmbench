# Audit: 2025-06-panoptic

## Initial totalSupply is set to 1,000,000 without minting tokens, causing permanent dilution of all shares
- **Location:** `HypoVault.sol` : `constructor`
- **Mechanism:** The constructor initializes `totalSupply = 1_000_000` but does not credit any address with these tokens. The `totalSupply` variable is used in all share price calculations (e.g., `fulfillDeposits`, `fulfillWithdrawals`), so these 1,000,000 “ghost” shares are permanently counted in the supply. They are never backed by any assets and can never be claimed, yet they dilute every subsequent deposit and withdrawal. Every depositor receives fewer shares than the assets they contribute, and every withdrawal redeems fewer assets than the true share of the vault’s value.
- **Impact:** All users suffer a permanent, proportional loss of value. The magnitude is initially ~0.1% after the first deposit and decays as more deposits occur, but the accounting invariant is broken and the vault’s share price is permanently distorted.

## Fulfillment functions can be manipulated via the `+ 1` offset to cause extreme share price distortion
- **Location:** `HypoVault.sol` : `fulfillDeposits`, `fulfillWithdrawals`
- **Mechanism:** The total assets used to compute the share price are calculated as:
  ```solidity
  totalAssets = accountant.computeNAV(...) + 1 - epochState.assetsDeposited - reservedWithdrawalAssets;
  ```
  The `+ 1` is intended to avoid division by zero, but when the NAV equals the sum of pending deposits and reserved withdrawals, `totalAssets` becomes 1. The manager can deliberately create this condition (e.g., by depositing exactly the amount of assets already in the vault) and then call `fulfillDeposits` with a large `assetsToFulfill`. The resulting `sharesReceived` will be `assetsToFulfill * totalSupply / 1`, minting an enormous number of shares for a tiny amount of assets. Similarly, `fulfillWithdrawals` can be called to burn a huge number of shares for a disproportionate amount of assets. 
- **Impact:** A malicious manager can repeatedly dilute existing shareholders or extract assets from the vault, effectively stealing all funds. The `+ 1` dust value turns into an unbounded manipulation vector.

## `executeDeposit` and `executeWithdrawal` can be permanently bricked by fulfilling with zero assets/shares
- **Location:** `HypoVault.sol` : `executeDeposit`, `executeWithdrawal`
- **Mechanism:** If the manager calls `fulfillDeposits` with `assetsToFulfill = 0`, the `assetsFulfilled` field of the epoch becomes 0. When `executeDeposit` later computes `sharesReceived = Math.mulDiv(userAssetsDeposited, sharesReceived, assetsFulfilled)`, the division by `assetsFulfilled` (0) reverts. The same issue occurs in `executeWithdrawal` if `sharesFulfilled` is set to 0 via `fulfillWithdrawals`. Users’ queued deposits/withdrawals in that epoch cannot be executed, and the remainder cannot be moved to the next epoch because the function reverts.
- **Impact:** Users’ funds become permanently stuck in the queued state, causing a complete loss of access to the deposited assets or the shares they intended to withdraw.
