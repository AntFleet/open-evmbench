# Audit: 2024-02-althea-liquid-infrastructure

## Consensus findings

## Burn / zero-value transfers permanently bloat the `holders` array with `address(0)`
*(consensus — Reviewer A and Reviewer B)*
- Location: `LiquidInfrastructureERC20.sol` : `_beforeTokenTransfer` (≈ lines 119–170 / 140–155) and `_afterTokenTransfer`; consumed by `distribute` / `distributeToAllHolders` (≈ lines 190–235)
- Mechanism: The approval check is guarded by `if (!(to == address(0)))`, but the holder-tracking push is **not**:
  ```solidity
  bool exists = (this.balanceOf(to) != 0);
  if (!exists) { holders.push(to); }
  ```
  On any burn `to == address(0)` and `balanceOf(address(0)) == 0`, so `address(0)` is appended to `holders`. `_afterTokenTransfer` only ever removes `from` (when its balance becomes zero), so these dead entries never get removed and accumulate. An approved holder can call `burn(0)` repeatedly: it reaches `_beforeTokenTransfer(account, address(0), 0)`, passes `_beforeMintOrBurn` whenever a distribution isn't currently due, and pushes another `address(0)` each time without ever reducing the caller's balance (so the caller is never removed either). Zero-value transfers to any approved-but-zero-balance address have the same effect.
- Impact: `holders` grows without bound. `distribute` iterates the entire `holders` array, and `distributeToAllHolders()` (used internally by `mintAndDistribute` and `burnAndDistribute`, and callable directly) executes `distribute(holders.length)` in a single transaction and will eventually revert out-of-gas; batched distribution also requires ever more iterations. A malicious approved holder can cheaply inflate the array before the distribution period elapses, raising everyone's distribution cost and making distributions impractical to complete. Because `_beforeTokenTransfer` reverts while `LockedForDistribution` is true, a wedged/never-completing distribution also locks minting, burning, and transfers for every holder.

## Additional findings (single-reviewer)

## Reverting distributable-token transfer can brick a partial distribution and freeze the whole token
*(Reviewer A only)*
- Location: `LiquidInfrastructureERC20.sol` : `distribute()` (the holder loop, ≈ lines 205–235), interacting with `_beginDistribution()`
- Mechanism: The per-holder payout is `if (toDistribute.transfer(recipient, entitlement)) { ... }`, which assumes `transfer` *returns false* on failure. Many real revenue tokens instead **revert** (USDC/USDT blacklisting of a recipient; USDT also returns no bool and fails ABI-decoding against the `IERC20` interface). When the transfer reverts, the entire `distribute` call reverts. Because `_beginDistribution()` sets `LockedForDistribution = true` and `nextDistributionRecipient` is persisted, a multi-batch distribution that already committed an earlier batch (e.g. `distribute(n)` with small `n`) is left in the `LockedForDistribution == true` state with `nextDistributionRecipient` pointing at the problematic holder. Every subsequent `distribute()` re-enters the loop at that index and reverts again, so the distribution can never reach `_endDistribution()`.
- Impact: While locked, `_beforeTokenTransfer` reverts on all transfers, mints, and burns — the token is fully frozen for every holder. Trigger conditions are realistic: a single holder blacklisted by a distributed stablecoin, or simply configuring USDT as a distributable ERC20. Recovery requires owner intervention (`disapproveHolder` on the stuck recipient so the `isApprovedHolder` guard skips them, or removing the token via `setDistributableERC20s`) — a recoverable but real denial-of-service that freezes all token activity in the meantime. Fix: use `SafeERC20` and/or skip failed recipients without reverting.

## `entitlement = balance / supply` truncates to zero, silently distributing nothing
*(Reviewer A only)*
- Location: `LiquidInfrastructureERC20.sol` : `_beginDistribution()` (≈ lines 260–272), `uint256 entitlement = balance / supply;`
- Mechanism: The per-unit entitlement is computed as `floor(distributableTokenBalance / totalSupply())`, and each holder then receives `erc20EntitlementPerUnit[j] * balanceOf(holder)`. `totalSupply()` is scaled to this token's 18 decimals, while distributable revenue tokens may have far fewer decimals (e.g. USDC = 6). Whenever the accumulated token balance is smaller than `totalSupply` (very common: 6-decimal balance vs. an 18-decimal supply, or a large supply relative to per-period revenue), the integer division yields `0`. The distribution then runs to completion, pays `0` to every holder, deletes `erc20EntitlementPerUnit`, and advances `LastDistribution` — i.e. it "succeeds" while distributing nothing.
- Impact: Revenue accrued in the contract can become effectively undistributable; it sits idle while the distribution machinery resets each cycle as if it had paid out. Even when the per-unit value is nonzero, the divide-then-multiply ordering discards a remainder proportional to `totalSupply`, permanently leaving dust in the contract. The math should scale up (e.g. distribute `balance * balanceOf(holder) / supply` per holder) rather than precomputing a truncated per-unit integer.

## `releaseManagedNFT` contains a dead invariant check (`require(true)`)
*(Reviewer A only)*
- Location: `LiquidInfrastructureERC20.sol` : `releaseManagedNFT()` (≈ lines 380–392)
- Mechanism: After the loop that searches `ManagedNFTs` for the released contract, the code reads:
  ```solidity
  // By this point the NFT should have been found and removed from ManagedNFTs
  require(true, "unable to find released NFT in ManagedNFTs");
  ```
  This is a no-op that always passes. Meanwhile `nft.transferFrom(address(this), to, nft.AccountId())` is executed *before* the search, so the NFT leaves the contract regardless of whether it is actually present in `ManagedNFTs`. The intended safety check — that the address being released is genuinely a managed NFT and was removed from bookkeeping — does not exist.
- Impact: The bookkeeping guarantee the comment claims is not enforced; the function can silently no-op on the array removal while still moving an NFT out of the contract, desyncing `ManagedNFTs` from reality. It is owner-only (not externally exploitable), but it is a broken safety check that defeats its stated purpose. Should be `require(found, ...)` with a `found` flag set in the loop.

## `withdrawFromManagedNFTs` is permissionless, not reentrancy-guarded, and updates the cursor after external calls
*(Reviewer A only)*
- Location: `LiquidInfrastructureERC20.sol` : `withdrawFromManagedNFTs()` (≈ lines 320–345)
- Mechanism: The function is `public` with no `nonReentrant` guard, iterates the managed NFTs calling `withdrawFrom.withdrawBalancesTo(...)` (which performs `IERC20(erc20).transfer(...)` for tokens drawn from each NFT's `getThresholds()`), and only writes `nextWithdrawal = i` *after* the loop completes. The set of ERC20s pulled is whatever is configured in each NFT's thresholds. A token in that set that executes attacker code on transfer can reenter `withdrawFromManagedNFTs` while `nextWithdrawal` is still stale, causing NFTs to be reprocessed and the `nextWithdrawal` cursor to be overwritten inconsistently between the inner and outer calls.
- Impact: No funds can be redirected (all withdrawals target `address(this)`), so this is low severity, but the cursor corruption can cause some NFTs to be skipped in a pass and emits misleading `Withdrawal` events. Preconditions: a threshold-listed token with a transfer hook/callback. Should follow checks-effects-interactions (update `nextWithdrawal` before external calls) and/or add `nonReentrant`.

## Released NFT may remain accounted during a multi-transaction withdrawal
*(Reviewer B only)*
- Location: `LiquidInfrastructureERC20.sol` : `releaseManagedNFT` / `withdrawFromManagedNFTs` (≈ lines 330–388, 290–322)
- Mechanism: `withdrawFromManagedNFTs` tracks progress with `nextWithdrawal`, but `releaseManagedNFT` removes an NFT by swap-and-pop without adjusting `nextWithdrawal`. If an owner releases an NFT while a multi-transaction withdrawal is partially complete, the array order and length can change underneath the cursor. A newly swapped NFT at an index lower than `nextWithdrawal` will be skipped for the remainder of that withdrawal cycle.
- Impact: Managed NFT balances can be omitted from the withdrawal batch and therefore excluded from the next holder distribution. This requires owner action during an in-progress withdrawal, but it creates real accounting drift between the intended managed NFT set and the funds actually pulled into the ERC20 distributor.

---

*Merge notes:* The `holders`/`address(0)` bloat was reported by both reviewers (same root cause and code path) and is consolidated as the single consensus finding, retaining Reviewer A's `burn(0)`/`distributeToAllHolders` specifics and Reviewer B's `_afterTokenTransfer` framing. The two `nextWithdrawal`/managed-NFT items are kept **separate** despite touching the same cursor: Reviewer A's is a reentrancy/CEI flaw in `withdrawFromManagedNFTs` (cursor updated after external token-transfer calls), whereas Reviewer B's is an owner-triggered `releaseManagedNFT` swap-and-pop that shifts the array under the cursor — distinct root causes, so neither is downgraded to consensus.

