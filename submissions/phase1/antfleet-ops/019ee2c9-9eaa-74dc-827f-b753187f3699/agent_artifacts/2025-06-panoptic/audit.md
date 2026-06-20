# Audit: 2025-06-panoptic

## Partial Deposit Carry-Forward Overmints Shares
- Location: [HypoVault.sol](/Users/augstar/open-evmbench/audit_sources/2025-06-panoptic/src/HypoVault.sol:472) : `fulfillDeposits`; [HypoVault.sol](/Users/augstar/open-evmbench/audit_sources/2025-06-panoptic/src/HypoVault.sol:310) : `executeDeposit`
- Mechanism: `fulfillDeposits` rolls the aggregate remainder forward as `assetsDeposited - assetsToFulfill`, but `executeDeposit` later computes each user’s fulfilled amount with per-user flooring and pushes each user’s own remainder into `queuedDeposit[user][epoch + 1]` without increasing `depositEpochState[epoch + 1].assetsDeposited`. After any partial fill, the sum of per-user carry-forwards can exceed the next epoch’s recorded aggregate deposits. On the next fulfillment, users are prorated against an understated denominator and can collectively mint more shares than the vault added to `totalSupply`.
- Impact: A depositor can split funds across many addresses, wait for a partial fulfillment, and mint unbacked shares in later epochs, diluting all existing holders and corrupting the vault’s share accounting.

## Partial Withdrawal Carry-Forward Lets Early Claimants Drain Later Reserves
- Location: [HypoVault.sol](/Users/augstar/open-evmbench/audit_sources/2025-06-panoptic/src/HypoVault.sol:516) : `fulfillWithdrawals`; [HypoVault.sol](/Users/augstar/open-evmbench/audit_sources/2025-06-panoptic/src/HypoVault.sol:348) : `executeWithdrawal`
- Mechanism: `fulfillWithdrawals` rolls the aggregate remainder forward as `sharesWithdrawn - sharesToFulfill`, but `executeWithdrawal` floors each user’s fulfilled shares independently and carries each user’s remainder into `queuedWithdrawal[user][epoch + 1]` without increasing `withdrawalEpochState[epoch + 1].sharesWithdrawn`. That makes the next epoch understate how many shares are still owed. The same function also burns basis using the global fulfillment ratio even when a specific user’s `sharesToFulfill` rounded to zero, so basis can be consumed without any payout.
- Impact: Early executors from an undercounted epoch can withdraw assets reserved for later users, causing later withdrawals to revert on `reservedWithdrawalAssets` underflow or to be underpaid. Users can also lose basis and be overcharged performance fees on later withdrawals.

## Fee-On-Transfer / Deflationary Underlyings Are Over-Credited
- Location: [HypoVault.sol](/Users/augstar/open-evmbench/audit_sources/2025-06-panoptic/src/HypoVault.sol:230) : `requestDeposit`
- Mechanism: The vault credits `queuedDeposit` and `depositEpochState.assetsDeposited` with the caller-supplied `assets` value before transfer, and never checks how many tokens were actually received. If the underlying token charges transfer fees, burns on transfer, or otherwise delivers less than requested, the vault still treats the full nominal amount as deposited.
- Impact: A depositor can receive shares backed by more assets than the vault actually received, diluting other holders and extracting value from future withdrawers.

## Zero-Fulfillment Epochs Permanently Brick Queued Claims
- Location: [HypoVault.sol](/Users/augstar/open-evmbench/audit_sources/2025-06-panoptic/src/HypoVault.sol:472) : `fulfillDeposits`; [HypoVault.sol](/Users/augstar/open-evmbench/audit_sources/2025-06-panoptic/src/HypoVault.sol:310) : `executeDeposit`; [HypoVault.sol](/Users/augstar/open-evmbench/audit_sources/2025-06-panoptic/src/HypoVault.sol:516) : `fulfillWithdrawals`; [HypoVault.sol](/Users/augstar/open-evmbench/audit_sources/2025-06-panoptic/src/HypoVault.sol:348) : `executeWithdrawal`
- Mechanism: The manager can advance an epoch with `assetsToFulfill == 0` or `sharesToFulfill == 0`. Once that happens, `executeDeposit` divides by `assetsFulfilled` and `executeWithdrawal` divides by `sharesFulfilled`, so both claim paths revert before reaching the carry-forward logic. Historical epochs cannot be canceled, only the current epoch can.
- Impact: Any deposits in a zero-filled deposit epoch become stuck forever, and any withdrawals in a zero-filled withdrawal epoch become unrecoverable after the shares were already burned.

## Unchecked `uint128` Downcasts Corrupt Supply and Reserve Accounting
- Location: [HypoVault.sol](/Users/augstar/open-evmbench/audit_sources/2025-06-panoptic/src/HypoVault.sol:491) : `fulfillDeposits`; [HypoVault.sol](/Users/augstar/open-evmbench/audit_sources/2025-06-panoptic/src/HypoVault.sol:539) : `fulfillWithdrawals`; [HypoVault.sol](/Users/augstar/open-evmbench/audit_sources/2025-06-panoptic/src/HypoVault.sol:257) : `requestWithdrawal`
- Mechanism: Fulfillment math is done in `uint256`, but epoch state stores `sharesReceived`, `assetsReceived`, and queued withdrawal `basis` in `uint128` without bounds checks. If those values exceed `2^128 - 1`, the stored epoch data truncates while `totalSupply` and `reservedWithdrawalAssets` are updated with the full `uint256` values. Later execution uses the truncated values, so the system cannot reconcile minted shares, owed assets, and recorded reserves.
- Impact: Large but type-valid deposits or withdrawals can permanently desynchronize claimable balances from `totalSupply` and reserved assets, leading to stranded assets, phantom supply, and broken future pricing.

## Profitable Withdrawals Default To Burning Fees Or Reverting
- Location: [HypoVault.sol](/Users/augstar/open-evmbench/audit_sources/2025-06-panoptic/src/HypoVault.sol:180) : `constructor`; [HypoVault.sol](/Users/augstar/open-evmbench/audit_sources/2025-06-panoptic/src/HypoVault.sol:348) : `executeWithdrawal`
- Mechanism: `feeWallet` is never initialized in the constructor, and `setFeeWallet` does not reject `address(0)`. On any profitable withdrawal, `executeWithdrawal` transfers the performance fee to `feeWallet`. With the default zero address, standard ERC20 underlyings revert on transfer; burn-tolerant tokens silently destroy the fee.
- Impact: Profitable withdrawals can be DoSed from deployment until governance sets a nonzero fee wallet, or fees can be permanently lost to the zero address.

