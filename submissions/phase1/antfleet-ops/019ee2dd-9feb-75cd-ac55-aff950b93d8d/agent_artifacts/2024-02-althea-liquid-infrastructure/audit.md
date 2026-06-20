# Audit: 2024-02-althea-liquid-infrastructure

 ## Distribution loop can be permanently frozen by a single reverting transfer
- **Location:** `LiquidInfrastructureERC20.sol` : `distribute(uint256)`
- **Mechanism:** `distribute` pays each holder sequentially in one transaction and only calls `_endDistribution()` after every holder is processed. For each recipient it calls `toDistribute.transfer(recipient, entitlement)` with no `try/catch` and no way to skip a bad recipient. If any distributable token reverts for one holder—e.g., a blacklisted address on USDC/USDT, a recipient contract with a reverting ERC-777 `tokensReceived` hook, or any custom token that reverts—the entire `distribute` call reverts and `nextDistributionRecipient` is not advanced.
- **Impact:** The contract remains `LockedForDistribution` forever, freezing all transfers, mints, and burns until the owner intervenes (and even then a blacklisted stablecoin may have to be removed from the distribution list, stranding that token’s revenue).

## Failed ERC-20 transfers are silently ignored
- **Location:** `LiquidInfrastructureERC20.sol` : `distribute(uint256)` (inner loop)
- **Mechanism:** The code uses `if (toDistribute.transfer(recipient, entitlement)) { receipts[j] = entitlement; }`. For tokens that signal failure by returning `false` instead of reverting, the failure is not propagated; the loop continues and the recipient simply records a zero receipt. `_endDistribution()` then updates `LastDistribution` and unlocks as if the distribution succeeded.
- **Impact:** Holders can be underpaid while the contract treats the period as settled. The unpaid balance remains in the contract, but future distributions recalculate entitlements against whatever `totalSupply` exists then, so accounting diverges from the intended per-holder payout.

## `setDistributableERC20s` can deadlock an in-progress distribution
- **Location:** `LiquidInfrastructureERC20.sol` : `setDistributableERC20s(address[])` / `distribute(uint256)`
- **Mechanism:** `setDistributableERC20s` has no guard against `LockedForDistribution`. `_beginDistribution` snapshots entitlements into `erc20EntitlementPerUnit` only for the token list that existed at start. If the owner later calls `setDistributableERC20s` to add tokens while a distribution is still running, the next batch of `distribute` will iterate `distributableERC20s` past the end of `erc20EntitlementPerUnit`, causing an out-of-bounds read and revert.
- **Impact:** An in-progress distribution can no longer reach `_endDistribution()`, leaving `LockedForDistribution == true` and permanently freezing transfers/mints/burns (or at least until the owner resets the list to exactly the previous length).

## Non-standard ERC-20s break distribution accounting
- **Location:** `LiquidInfrastructureERC20.sol` : `_beginDistribution()` and `distribute(uint256)`
- **Mechanism:** Entitlements are computed as `IERC20(distributableERC20s[i]).balanceOf(address(this)) / totalSupply()` and later paid exactly with `transfer(recipient, entitlement)`. This assumes the distributable token has 18-decimal fixed supply, no transfer fee, and delivers exactly `entitlement`. Fee-on-transfer, rebasing, or deflationary tokens cause the actual balance to differ from the entitlement snapshot, while the contract still emits `receipts[j] = entitlement`.
- **Impact:** Revenue accounting becomes inconsistent: some periods cannot fulfill the stated entitlements, earlier holders may capture more than their share, and later holders receive less than expected. The owner-set token list has no duplicate or token-type checks, so duplicates will pay the same token more than once and quickly drain that allocation for later recipients.

## Unbounded `holders` array blocks all-holder convenience functions
- **Location:** `LiquidInfrastructureERC20.sol` : `distributeToAllHolders()`, `mintAndDistribute(...)`, `burnAndDistribute(...)`, `burnFromAndDistribute(...)`
- **Mechanism:** `_beforeTokenTransfer` pushes every new zero-balance recipient into `holders`, so the array grows linearly with each transfer/mint to a new address. The convenience functions call `distributeToAllHolders()`, which executes `distribute(holders.length)` and attempts to process every holder in a single block.
- **Impact:** Once `holders` is large enough, `distributeToAllHolders`, `mintAndDistribute`, `burnAndDistribute`, and `burnFromAndDistribute` will exceed the block gas limit and revert. Users can still fall back to batched `distribute`, but these functions become permanently unusable and owner mint/burn workflows that rely on them are DoS’d.

## `releaseManagedNFT` succeeds for NFTs that are not managed
- **Location:** `LiquidInfrastructureERC20.sol` : `releaseManagedNFT(address,address)`
- **Mechanism:** The function transfers the NFT before checking `ManagedNFTs` membership, then loops through `ManagedNFTs` to remove the entry. After the loop it has `require(true, "unable to find released NFT in ManagedNFTs")`, which is a tautology and can never revert. If `nftContract` is any `LiquidInfrastructureNFT` that the contract owns but that is not in `ManagedNFTs`, the transfer still executes and the function emits `ReleaseManagedNFT`.
- **Impact:** The owner can accidentally release an arbitrary NFT and emit a misleading event while `ManagedNFTs` remains unchanged. More importantly, the function performs no `LockedForDistribution` or membership validation, so releasing during a distribution or with the wrong NFT does not revert, leaving the managed-nft bookkeeping inconsistent.
