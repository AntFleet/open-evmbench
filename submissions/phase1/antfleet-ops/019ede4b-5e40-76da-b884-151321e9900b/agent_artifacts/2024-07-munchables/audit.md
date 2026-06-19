# Audit: 2024-07-munchables

## Snuggery Size Limit Bypass
- Location: `src/managers/SnuggeryManager.sol` : `increaseSnuggerySize`
- Mechanism: The function validates the user's current snuggery size against the global maximum using `if (previousSize >= MAX_SNUGGERY_SIZE) revert SnuggeryMaxSizeError();`. However, it fails to check if the newly requested size (`previousSize + _quantity`) exceeds the maximum. A user whose current size is at least one slot below the maximum can pass a large `_quantity` value, pay the points cost, and push their `maxSnuggerySize` far beyond the intended global limit.
- Impact: Attackers can bypass the maximum snuggery capacity limit, allowing them to import and stake significantly more NFTs than intended. This directly inflates their chonk generation and point yields, breaking the game's economic balance and emission schedules.

## LandManager Configuration and Division by Zero
- Location: `src/managers/LandManager.sol` : `_reconfigure`
- Mechanism: The contract fetches critical configuration parameters (`MIN_TAX_RATE`, `MAX_TAX_RATE`, `BASE_SCHNIBBLE_RATE`, `PRICE_PER_PLOT`) using `StorageKey` enums that are intended for contract addresses (e.g., `StorageKey.LockManager`, `StorageKey.AccountManager`). Because `ConfigStorage` segregates `uintStorage` and `addressStorage` by the same enum key space, these `getUint` calls will read from uninitialized uint slots and default to `0`. Crucially, `PRICE_PER_PLOT` will be `0`, which is later used as a divisor in `_getNumPlots`.
- Impact: Complete Denial of Service for the `LandManager`. Any user interaction that calls `_getNumPlots` (such as `stakeMunchable`, `transferToUnoccupiedPlot`, or `updateTaxRate`) will revert due to a division by zero panic. Additionally, tax rate bounds will be broken, restricting tax rates strictly to 0.

## Rescue Function DoS via Incorrect ERC20 Transfer
- Location: `src/managers/MigrationManager.sol` : `rescue`
- Mechanism: The admin `rescue` function attempts to recover stuck ERC20 tokens using `IERC20(_tokenContract).transferFrom(address(this), _returnAddress, _quantity)`. The `transferFrom` function requires the caller (`msg.sender`, the admin) to have an allowance granted by the `from` address (`address(this)`). Since the `MigrationManager` never approves the admin to spend its own tokens, this call will always revert for standard ERC20 implementations. It should use `transfer` instead.
- Impact: The admin cannot rescue stuck or accidentally sent ERC20 tokens from the `MigrationManager` contract, leading to a permanent loss of those funds.

## Sub-Accounts Pagination Out-of-Bounds Panic
- Location: `src/managers/AccountManager.sol` : `getSubAccounts`
- Mechanism: The view function initializes a fixed-size memory array `address[20] memory _subAccounts` and iterates using an index `i` that starts from the `_start` pagination parameter. Inside the loop, it assigns `_subAccounts[i] = subAccounts[_player][i]`. If a frontend requests pagination (e.g., `_start = 20`), `i` starts at 20. Attempting to write to `_subAccounts[20]` on a 20-element array (valid indices 0-19) causes an out-of-bounds array access panic. The assignment should be `_subAccounts[i - _start]`.
- Impact: Denial of Service for the `getSubAccounts` view function whenever pagination is used. Frontends, subgraphs, or off-chain scripts relying on this function to paginate through a user's sub-accounts will fail and revert, breaking UI functionality.
