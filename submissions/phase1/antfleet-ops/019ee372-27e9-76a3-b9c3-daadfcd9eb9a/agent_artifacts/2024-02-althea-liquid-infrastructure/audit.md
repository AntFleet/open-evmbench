# Audit: 2024-02-althea-liquid-infrastructure

Here are the vulnerabilities found in the provided codebase.

## Multiple `holders` Array Pushes allow Rewards Drain and DoS
- Location: `LiquidInfrastructureERC20.sol` : `_beforeTokenTransfer`
- Mechanism: In `_beforeTokenTransfer`, the contract checks if the `to` address currently has no balance (`this.balanceOf(to) == 0`) and if so, it adds the address to the `holders` array. However, there is no check preventing zero-value transfers. If a user transfers `0` tokens to an approved address (e.g. themselves or another Sybil address), the recipient's balance remains `0`. Therefore, `exists` remains `false` and the recipient is pushed to the `holders` array again. Repeated zero-value transfers will insert the same address into the `holders` array an arbitrary number of times. 
- Impact: An attacker can artificially inflate their occurrences in the `holders` array prior to receiving any actual tokens. Because `distribute` calculates the payout based on `erc20EntitlementPerUnit[j] * this.balanceOf(recipient)` for every entry in the array, an attacker with `N` duplicates will receive `N * actual_entitlement`, draining the protocol's rewards. Additionally, bloating the `holders` array will permanently lock the contract in a Denial of Service (DoS) state, throwing out-of-gas errors during the distribution phase.

## Incorrect Removal Logic in `_afterTokenTransfer` Skips Adjacent Duplicates
- Location: `LiquidInfrastructureERC20.sol` : `_afterTokenTransfer`
- Mechanism: When a user's token balance drops to 0, the `_afterTokenTransfer` function attempts to remove the user from the `holders` array by swapping the item to be deleted with the last item in the array and calling `.pop()`. Crucially, after a swap occurs, the iterating index `i` unconditionally increments to check the next element in the array (`i++`). This skips the inspection of the element that was just swapped into the current `i` index.
- Impact: If there are multiple entries for the same address in the `holders` array, or if the swapped last element happens to be the same identity scheduled for removal, the skipped element will persist in the `holders` array despite the user now having a balance of 0. This can lead to unremovable array bloat or logical mismatches during distribution operations.

## `address(0)` is Pushed to `holders` on Token Burn Operations
- Location: `LiquidInfrastructureERC20.sol` : `_beforeTokenTransfer`
- Mechanism: When tokens are burned, the internal transfer is executed with the target address `to` set to `address(0)`. While the code checks `if (!(to == address(0)))` to bypass the `isApprovedHolder` requirement, it does not bypass the logic that adds the recipient to `holders`. Since `this.balanceOf(address(0))` evaluates to `0`, `address(0)` is inadvertently pushed into the `holders` array. 
- Impact: Every time tokens are burned, `address(0)` is appended to the `holders` array. When `distribute` is called, the contract iterates over `address(0)` and tries to execute ERC20 transfers to the zero address. Because most standard ERC20 tokens revert on transfers to the zero address, this will cause the `distribute` function to completely revert, locking distributions, transfers, mints, and burns for the entire protocol.
