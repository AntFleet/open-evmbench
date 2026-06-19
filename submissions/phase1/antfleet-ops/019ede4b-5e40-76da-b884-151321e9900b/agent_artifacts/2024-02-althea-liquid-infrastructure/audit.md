# Audit: 2024-02-althea-liquid-infrastructure

## Unbounded Array Growth of `address(0)` Leading to Distribution DoS
- Location: `LiquidInfrastructureERC20.sol` : `_beforeTokenTransfer`
- Mechanism: During a token burn operation, the `to` parameter is `address(0)`. The function evaluates `bool exists = (this.balanceOf(to) != 0);`. Because the zero address inherently has a balance of 0, `exists` evaluates to false, causing `address(0)` to be pushed into the `holders` array. The corresponding `_afterTokenTransfer` hook only checks and removes the `from` address (the burner) and never removes `address(0)`. Consequently, every token burn permanently appends a duplicate `address(0)` entry to the `holders` array.
- Impact: The `holders` array will grow indefinitely with zero addresses. Since `distribute` and `distributeToAllHolders` iterate over the entire `holders` array to pay out rewards, this unbounded growth will eventually cause these functions to exceed the block gas limit. This results in a permanent Denial of Service that freezes all reward distributions for all token holders.

## Distribution Array Length Mismatch Causing DoS or Skipped Rewards
- Location: `LiquidInfrastructureERC20.sol` : `setDistributableERC20s`
- Mechanism: The `setDistributableERC20s` function allows the owner to overwrite the `distributableERC20s` array at any time, without checking if `LockedForDistribution` is true. If the owner modifies the array while a multi-block distribution is in progress, the `distribute` function will iterate using the new `distributableERC20s.length` but access the `erc20EntitlementPerUnit` array, which was sized and populated based on the old array at the start of the distribution in `_beginDistribution`.
- Impact: If the new array is longer than the old one, `distribute` will trigger an out-of-bounds array access and revert on every subsequent call, permanently bricking the distribution process and locking all accrued rewards in the contract. If the new array is shorter, the function will silently skip distributing rewards for the removed tokens, causing those funds to be stuck or misallocated.

## Flawed Swap-and-Pop Logic Skips Array Elements During Removal
- Location: `LiquidInfrastructureERC20.sol` : `_afterTokenTransfer`
- Mechanism: When a holder's balance reaches zero, the contract attempts to remove them from the `holders` array using a swap-and-pop technique: `holders[i] = holders[holders.length - 1]; holders.pop();`. However, the loop fails to `break` or decrement `i` after the swap. Consequently, the `for` loop increments `i` on the next iteration, skipping the validation of the element that was just moved into index `i`.
- Impact: While this primarily causes gas inefficiency for unique addresses, it becomes a critical logic error when duplicate entries exist in the array (such as the accumulated `address(0)` entries from the first vulnerability). The skipped validation prevents proper cleanup of duplicate zero addresses if they are ever targeted for removal, exacerbating the unbounded array growth and making the array state unpredictable during iteration.
