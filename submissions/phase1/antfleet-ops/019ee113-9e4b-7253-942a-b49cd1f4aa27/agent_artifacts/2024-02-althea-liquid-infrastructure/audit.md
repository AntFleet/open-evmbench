# Audit: 2024-02-althea-liquid-infrastructure

# Security Audit Report

## Distribution bricked by mid-distribution change of `distributableERC20s`
- **Location**: `LiquidInfrastructureERC20.sol` : `setDistributableERC20s` and `distribute`
- **Mechanism**: `_beginDistribution` snapshots the current `distributableERC20s` list and computes `erc20EntitlementPerUnit` indexed by position. The owner can call `setDistributableERC20s` at any time — including while `LockedForDistribution == true` — to overwrite the list. The distribution loop in `distribute` then iterates over the *new* list but reads from the *old* `erc20EntitlementPerUnit` array. If the new list is longer than the old one, the read `erc20EntitlementPerUnit[j]` reverts with an array out-of-bounds panic (Solidity 0.8 checked arithmetic). The whole `distribute` call reverts before `nextDistributionRecipient` is updated, so the distribution can never complete. The contract is then permanently stuck with `LockedForDistribution == true`, blocking all transfers, mints, and burns. Recovery requires the owner to guess the original list length and shrink the list accordingly, which is brittle and not guaranteed to be possible.
- **Impact**: Permanent DoS / loss of funds. Once triggered, no holder can transfer, mint, burn, or be distributed to until a new contract is deployed.

## DoS via unbounded growth of `holders` array with `address(0)`
- **Location**: `LiquidInfrastructureERC20.sol` : `_beforeTokenTransfer`
- **Mechanism**: The hook unconditionally pushes `to` into `holders` whenever `balanceOf(to) == 0`. For burns, `to == address(0)`, and `balanceOf(address(0))` is always 0 (the ERC20 standard forbids balance at address 0), so `address(0)` is pushed on every burn. Any holder can call `burn(0)` (which is a no-op for token state but still triggers the hook) arbitrarily many times to inflate the array. There is no deduplication or `to != address(0)` guard. During `distribute`, the loop iterates the entire array, and `isApprovedHolder(address(0))` always returns false, so each spurious entry wastes gas. Once the array exceeds a few thousand entries, processing a single recipient in `distribute(numDistributions)` may already cost more gas than a single distribution call needs; completing a full distribution over a very large array will exceed the block gas limit, preventing the distribution from finishing.
- **Impact**: Griefing DoS. An attacker (or a buggy user) can permanently brick the distribution mechanism at very low cost, freezing all token movement.

## Self-transfer removes holder from distribution list
- **Location**: `LiquidInfrastructureERC20.sol` : `_afterTokenTransfer`
- **Mechanism**: The hook removes `from` from `holders` whenever `balanceOf(from) == 0`. It does not check whether `from == to`. For a self-transfer (`from == to`, `amount > 0`), the balance is unchanged, so `stillHolding` is true and the removal branch still runs because the guard only checks the balance, not whether the transfer was to self. The holder is therefore popped from the array even though they still hold tokens.
- **Impact**: Loss of revenue share. The affected holder retains their tokens but is silently dropped from all future distributions until they next receive tokens from another holder (which re-adds them via the `balanceOf(to) != 0` check in `_beforeTokenTransfer`).

## `releaseManagedNFT` has a tautological `require`
- **Location**: `LiquidInfrastructureERC20.sol` : `releaseManagedNFT`
- **Mechanism**: After the swap-and-pop loop that searches for `nftContract` in `ManagedNFTs`, the function executes `require(true, "unable to find released NFT in ManagedNFTs")`. The condition is always true, so the intended check (that the NFT was actually found and removed) is missing. If the owner passes an NFT address that is not in `ManagedNFTs`, the NFT is still transferred out of the contract and the `ReleaseManagedNFT` event is emitted, but `ManagedNFTs` is not modified.
- **Impact**: Inconsistent accounting. The owner may believe the NFT is no longer managed while it is still in the array, leading to confusion in subsequent `withdrawFromManagedNFTs` calls and potentially re-releasing the same NFT.

## `addManagedNFT` does not check for duplicates
- **Location**: `LiquidInfrastructureERC20.sol` : `addManagedNFT`
- **Mechanism**: The function only verifies that the contract owns the NFT and pushes it onto `ManagedNFTs` without checking whether the address already exists in the array. A duplicate entry causes the same NFT to be processed multiple times in `withdrawFromManagedNFTs` (the second pass is a no-op for balances but still costs gas and emits duplicate `Withdrawal` events). The duplicate also cannot be cleanly removed by `releaseManagedNFT` because the loop breaks after the first match, leaving a stale entry.
- **Impact**: Gas waste, event log pollution, and inability to fully remove a duplicate NFT via `releaseManagedNFT`.

## `withdrawFromManagedNFTs` lacks reentrancy protection
- **Location**: `LiquidInfrastructureERC20.sol` : `withdrawFromManagedNFTs`
- **Mechanism**: The function makes external calls to `withdrawFrom.withdrawBalancesTo(...)` and the underlying ERC20 `transfer` calls inside it. The state update `nextWithdrawal = i` happens after the loop. A malicious or callback-enabled ERC20 (or a malicious `LiquidInfrastructureNFT`) could re-enter the contract and call `distribute` or `mint`/`burn`. While direct storage corruption is unlikely because `distribute`/`mint` hold the `nonReentrant` lock and the lock is only acquired once per outer call, cross-function reentrancy is possible: an external call inside the loop can re-enter `distribute` (or any non-guarded function) while the contract is in the middle of a withdrawal sweep. More importantly, the absence of a guard is a deviation from the pattern used elsewhere in the contract and a footgun for future modifications.
- **Impact**: Cross-function reentrancy. The current state changes are not directly exploitable, but the missing guard is a defense-in-depth gap that could become critical if the function is extended.

## Silent distribution failure on insufficient balance
- **Location**: `LiquidInfrastructureERC20.sol` : `distribute`
- **Mechanism**: The loop uses the unchecked return value of `IERC20.transfer`; if it returns false (e.g., because the owner or anyone transferred distributable tokens out, or the token is fee-on-transfer / rebasing), the receipt is recorded as 0 and the loop continues silently. The `Distribution` event logs the zero amount but no revert occurs, and the `LockedForDistribution` flag is still cleared at the end. The residual entitlement (`balance % supply` at distribution start, or any tokens drained after) is permanently stuck in the contract.
- **Impact**: Permanent loss of distributed revenue for the affected recipients. Because the lock is cleared, the next distribution will compute entitlements over a new (smaller) balance, and the stuck tokens are unrecoverable. This is also a griefing vector for an owner who drains balances between distributions.
