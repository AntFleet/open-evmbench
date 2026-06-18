# Audit: 2024-02-althea-liquid-infrastructure

## 1. Malicious holder can permanently lock the contract by causing a revert in `distribute`
- **Location:** `LiquidInfrastructureERC20.sol` : `distribute`
- **Mechanism:**  
  During distribution, the loop calls `IERC20.transfer(recipient, entitlement)` for each holder. If a holder is a contract that reverts (e.g., by design or due to a malicious fallback) the `transfer` will revert, rolling back the entire transaction. Because `nextDistributionRecipient` is only updated after a successful iteration, the distribution cannot progress past this holder. The contract remains `LockedForDistribution = true`, which prevents all transfers, mints, and burns. The offending holder cannot be removed from the `holders` array because transfers (and therefore balance changes) are disabled. The contract becomes deadlocked permanently.
- **Impact:**  
  A malicious (or simply misbehaving) holder can freeze the contract indefinitely, locking all funds and making the token non‑transferable and non‑distributable. This is a denial‑of‑service that can be triggered by any approved holder with a non‑zero balance.

## 2. Reentrancy in `withdrawFromManagedNFTs` allows state manipulation
- **Location:** `LiquidInfrastructureERC20.sol` : `withdrawFromManagedNFTs`
- **Mechanism:**  
  The function calls `withdrawFrom.withdrawBalancesTo(...)` on an external `LiquidInfrastructureNFT` contract before updating the `nextWithdrawal` state variable. There is no reentrancy guard. A malicious ManagedNFT contract can re‑enter `withdrawFromManagedNFTs` during the external call, causing the same NFT to be processed multiple times or disrupting the `nextWithdrawal` counter (e.g., skipping NFTs or double‑counting).
- **Impact:**  
  If a ManagedNFT is compromised (or an owner accidentally adds a malicious NFT), an attacker can manipulate the withdrawal sequence, potentially leading to lost funds or accounting errors in the collected balances.

## 3. `holders` array removal loop can corrupt the array
- **Location:** `LiquidInfrastructureERC20.sol` : `_afterTokenTransfer`
- **Mechanism:**  
  The loop that removes a holder when their balance becomes zero copies the last element into the found index and pops the array, but does **not** `break`. It continues iterating with the modified array. While the code assumes each address appears only once, the missing `break` means that if an address appeared twice (e.g., due to a separate bug) the removal would either leave the duplicate or corrupt the array. Even without duplicates, the loop unnecessarily re‑evaluates the moved element, which is inefficient and deviates from the expected “remove once” logic.
- **Impact:**  
  In the unlikely event of duplicate entries, the `holders` array could become corrupted, leading to incorrect distribution payouts or inability to properly track holders.

## 4. Owner can change `distributableERC20s` during an active distribution
- **Location:** `LiquidInfrastructureERC20.sol` : `setDistributableERC20s`
- **Mechanism:**  
  The `distribute` function uses the `distributableERC20s` storage array to determine which tokens to distribute. The function `setDistributableERC20s` is not restricted by `LockedForDistribution`. If the owner modifies the array after `_beginDistribution` has already computed the `erc20EntitlementPerUnit` based on the old list, the distribution loop will iterate over the new list, causing a mismatch in length between the entitlements array and the tokens. This can result in an out‑of‑bounds access (revert) or in distributing incorrect amounts to holders.
- **Impact:**  
  A mistaken or malicious owner can break an ongoing distribution, potentially reverting transactions or paying out wrong entitlements. While the owner is trusted, the lack of a guard makes the protocol fragile.
