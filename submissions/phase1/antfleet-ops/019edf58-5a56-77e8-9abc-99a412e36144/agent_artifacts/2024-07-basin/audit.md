# Audit: 2024-07-basin

## Stable2 `decodeWellData` decimal1 fallback bug
- Location: `src/functions/Stable2.sol` : `decodeWellData`
- Mechanism: The function decodes two decimals from well data and defaults each to 18 if zero. However, the second conditional checks `decimal0 == 0` again instead of `decimal1 == 0`. When `decimal1` is 0, it is not corrected to 18. Later, `getScaledReserves` computes `reserves[1] * 10**(18 - 0) = reserves[1] * 10**18`, which will overflow for any non-trivial reserve value, causing every Stable2 well operation (swap, add/remove liquidity, oracle reads) to revert.
- Impact: A Stable2 well configured with well-data encoding `decimal1 = 0` (either intentionally or accidentally) is permanently bricked. All AMM and oracle functions that call `decodeWellData` will revert due to overflow in `getScaledReserves`.

## ConstantProduct `calcReserve` rounds down instead of up
- Location: `src/functions/ConstantProduct.sol` : `calcReserve`
- Mechanism: The `IWellFunction` interface requires `calcReserve` to round up so that `calcLpTokenSupply(reserves) >= totalSupply()` is maintained. `ConstantProduct.calcReserve` uses plain integer division (`reserve / reserves[i]`) which rounds down. In `_swapFrom`, `reserves[j] = _calcReserve(...)` is set to this rounded-down value, making `amountOut = reserveJBefore - reserves[j]` larger than it should be. Every swap extracts slightly more value than the invariant dictates.
- Impact: An attacker can repeatedly swap through a ConstantProduct Well to systematically extract value from LP holders. Each swap overpays the swapper by up to `n-1` units of the output token (one unit of rounding per division), which is extracted from the pool's reserves at the expense of LPs.

## WellUpgradeable `init` has no access control
- Location: `src/WellUpgradeable.sol` : `init`
- Mechanism: `WellUpgradeable` is bored with `initNoWellToken()` (an `initializer`, version 1). The separate `init(string,string)` function uses `reinitializer(2)` but has no access-control modifier. Anyone can call it to re-initialize the contract, which calls `__ERC20Permit_init`, `__ERC20_init`, `__ReentrancyGuard_init`, `__UUPSUpgradeable_init`, and `__Ownable_init` — setting the caller as owner and overwriting the EIP-712 domain separator and ERC20 metadata.
- Impact: Any attacker can change a WellUpgradeable's ERC20 name/symbol and, critically, invalidate all outstanding EIP-2612 permits by changing the domain separator. The attacker also becomes the contract owner. While current `upgradeTo`/`_authorizeUpgrade` checks prevent direct upgrade exploitation on minimal proxies, ownership and domain-separator control are security-relevant for any downstream integration that relies on them.

## `removeLiquidityImbalanced` transfers tokens before burning LP
- Location: `src/Well.sol` : `removeLiquidityImbalanced`
- Mechanism: The function transfers all `tokenAmountsOut` to the recipient via `safeTransfer` *before* computing `lpAmountIn` and burning LP tokens. If any output token implements a callback during `transfer` (e.g., ERC-777 hooks), the callback can re-enter view-like functions. Although the `nonReentrant` guard prevents re-entering state-changing Well functions, the callback can observe an inconsistent state where tokens have left the Well but LP tokens have not yet been burned, and the on-chain `getReserves()` / `getRemoveLiquidityImbalancedIn` view functions still reflect pre-removal reserves.
- Impact: A malicious ERC-777-style output token can observe a transient state during `removeLiquidityImbalanced` where the Well's token balances are lower than recorded reserves but the LP supply has not yet decreased. Any external protocol that reads Well state during this callback (e.g., an oracle or lending market) will see stale/incorrect reserves, potentially enabling manipulation of dependent systems.
