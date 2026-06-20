# Audit: 2024-02-althea-liquid-infrastructure

I audited the two core contracts (`LiquidInfrastructureERC20`, `LiquidInfrastructureNFT`) and their helper `OwnableApprovableERC721`. The `TestERC20*`/`TestERC721A` files are test mints and out of scope. Genuine findings below.

## `address(0)` is pushed into `holders` on every burn → permanent distribution lock (DoS)
- Location: `LiquidInfrastructureERC20.sol` : `_beforeTokenTransfer`
- Mechanism: The holder-bookkeeping block runs unconditionally for all transfers, including burns:
  ```solidity
  bool exists = (this.balanceOf(to) != 0);
  if (!exists) { holders.push(to); }
  ```
  On a burn, `to == address(0)`. `balanceOf(address(0))` is always `0`, so `exists` is always `false` and a fresh `address(0)` entry is appended to `holders` on *every single burn* (the earlier `if (!(to == address(0)))` guard only skips the allowlist check, not this push). The `holders` array therefore grows without bound, polluted with dead `address(0)` entries.
- Impact: `holders` is iterated linearly in `distribute`/`distributeToAllHolders` and in `_afterTokenTransfer`'s removal loop. As the array bloats, a distribution can no longer be completed in one transaction. Crucially, `distribute` sets `LockedForDistribution = true` in `_beginDistribution` and only clears it in `_endDistribution` once `nextDistributionRecipient == holders.length`. If the paginated pay-out loop can never reach the end within the block gas limit, the contract stays locked forever: all transfers, mints, and burns are permanently frozen (`_beforeTokenTransfer` reverts on `LockedForDistribution`), and accrued ERC20 rewards are stranded. An attacker who is an approved holder (or the burn path generally) can deliberately accelerate this with repeated tiny burns.

## `setDistributableERC20s` is not guarded against in-progress distributions → bricked / mis-paid distribution
- Location: `LiquidInfrastructureERC20.sol` : `setDistributableERC20s`
- Mechanism: `erc20EntitlementPerUnit` is sized to `distributableERC20s.length` once in `_beginDistribution`. Distributions are paginated across multiple `distribute()` calls while `LockedForDistribution` stays true, but `setDistributableERC20s` has no `require(!LockedForDistribution)` check. If the list is changed between pages, the `distribute` loop iterates `j < distributableERC20s.length` (the *new* list) while indexing `erc20EntitlementPerUnit[j]` (sized to the *old* list). Growing the list causes an out-of-bounds revert that bricks the current (locked) distribution; reordering it pays the wrong per-unit entitlement for the wrong token.
- Impact: An in-progress distribution can be made permanently un-completable (leaving the contract locked, same end-state as the finding above), or holders can be paid incorrect amounts of the wrong tokens. Owner-triggered, but it is an unguarded state machine that can lock all funds.

## `_afterTokenTransfer` removal loop has no `break` and re-reads mutated length
- Location: `LiquidInfrastructureERC20.sol` : `_afterTokenTransfer`
- Mechanism: After swap-and-pop removal of `from`, the loop continues iterating instead of breaking. The element swapped into index `i` is never re-examined, and the loop keeps scanning the (now shortened) array. Combined with the `address(0)` pollution above, mints (`from == address(0)`, whose `balanceOf` is `0`) enter this loop and remove an arbitrary `address(0)` slot, so the holder set becomes order-dependent and inconsistent.
- Impact: Holder set corruption / unnecessary O(n) gas on every transfer, compounding the DoS surface. Lower severity on its own but it interacts directly with the unbounded-array problem.

## `releaseManagedNFT` success guard is a no-op
- Location: `LiquidInfrastructureERC20.sol` : `releaseManagedNFT`
- Mechanism: The post-loop check is `require(true, "unable to find released NFT in ManagedNFTs")`, which can never revert. If `nftContract` is not present in `ManagedNFTs`, the function still transfers the NFT out and reports success without any accounting update.
- Impact: Inconsistent `ManagedNFTs` accounting versus actual NFT ownership; the intended invariant (NFT must have been a managed entry) is not enforced. Owner-only, low severity.

---

Notes on things I checked and deemed **not** vulnerabilities: `distribute`/`mint` are `nonReentrant` and `withdrawFromManagedNFTs`/burn revert while `LockedForDistribution`, so the malicious-ERC20 reentrancy path is contained; entitlement is snapshotted at `_beginDistribution` with transfers frozen, so no double-claim or balance-gaming across pages; floor division in `_beginDistribution` only strands dust. The strongest, clearly-unintended issue is the `address(0)` holder pollution and its resulting permanent lock.

