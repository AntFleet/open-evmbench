# Audit: 2023-07-pooltogether

Here are the security vulnerabilities found in the provided codebase.

## Malicious Winner Can DoS Batch Prize Claims via Reverting Hooks
- **Location:** `Vault.sol` : `_claimPrize`
- **Mechanism:** The `Vault` allows users to set arbitrary smart contracts as their `VaultHooks` implementation via `setHooks()`. When the central `claimer` calls `claimPrizes()` to process a batch of winners, the vault makes external calls to `hooks.implementation.beforeClaimPrize()` and `hooks.implementation.afterClaimPrize()` for each winner. Because these external calls are not wrapped in a `try/catch` block, a malicious winner can configure a custom hook implementation that intentionally reverts or consumes all available gas. 
- **Impact:** Since the `claimer` processes multiple winners in a single transaction/batch, a single malicious winner can cause the entire `claimPrizes()` transaction to revert. This denial-of-service (DoS) attack prevents other legitimate winners in the same batch from receiving their prizes. If unresolved within the claiming window, those users will permanently lose their prizes.

## Attackers Can Steal Direct Vault Asset Transfers Due to Flawed Deposit Logic
- **Location:** `Vault.sol` : `_deposit`
- **Mechanism:** When a user calls `deposit()` or `mint()`, the `_deposit` function calculates how many assets it needs to pull from the user by subtracting the `Vault` contract's existing internal asset balance (`_vaultAssets`) from the requested `_assets` amount. If `_assets` is less than or equal to `_vaultAssets`, the condition `_assets > _vaultAssets` is false, and the `Vault` bypasses pulling *any* funds from the caller. Instead, it takes the tokens currently resting in the contract, deposits them into the `_yieldVault`, and mints the corresponding new shares strictly to the caller's `_receiver`.
- **Impact:** Any underlying assets residing in the `Vault` (e.g., from user transfer mistakes, liquidations, airdrops, donations, or asynchronous yields) can be instantly stolen by an attacker. By simply calling `deposit(vaultBalance)`, the attacker gets shares minted to them perfectly corresponding to the existing idle assets, fully at the expense of those existing assets, without spending any of their own tokens.
