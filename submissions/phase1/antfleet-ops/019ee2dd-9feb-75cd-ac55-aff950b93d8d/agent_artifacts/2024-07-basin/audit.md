# Audit: 2024-07-basin

 ## `ConstantProduct.calcReserve` rounds down instead of up
- Location: `src/functions/ConstantProduct.sol` : `calcReserve`
- Mechanism: The function computes the target reserve as `reserve = (lpTokenSupply / n) ** n` and then repeatedly divides by the other reserves with plain `/`. Every division truncates downward, so the returned reserve is rounded down instead of rounded up as required by `IWellFunction`. `Well._swapFrom`, `getSwapOut`, `removeLiquidityOneToken`, and `getRemoveLiquidityOneTokenOut` use this value to compute the amount of tokens sent to users, so a rounded-down reserve produces an inflated output amount.
- Impact: Traders and single-token liquidity removers consistently receive slightly more than the invariant allows. Over many operations this rounding error drains the pool’s reserves and can break the `calcLpTokenSupply(...) >= totalSupply()` invariant.

## `Stable2.decodeWellData` typo mis-scales the second token
- Location: `src/functions/Stable2.sol` : `decodeWellData`
- Mechanism: The function intends to default a missing decimals value to 18, but the second check repeats `if (decimal0 == 0)` instead of `if (decimal1 == 0)`. Consequently, when `decimal1` is supplied as `0`, it stays `0` and `getScaledReserves` multiplies the second reserve by `10 ** 18` instead of by `1`.
- Impact: A Stable2 Well whose well-function data encodes a 0/missing decimal for the second token will use reserves scaled by `1e18` in the stableswap invariant. This severely misprices swaps and liquidity operations, allowing an attacker who deploys such a Well to mint disproportionate LP or extract value from other participants.

## `LibWellConstructor` packs token addresses tightly while `Well.sol` reads them at 32-byte offsets
- Location: `src/libraries/LibWellConstructor.sol` : `encodeWellImmutableData`; `src/libraries/LibWellUpgradeableConstructor.sol` : `encodeWellImmutableData`; `src/Well.sol` : `tokens`, `wellFunction`, `pumps`
- Mechanism: The constructors use `abi.encodePacked(..., _tokens, ...)` to pack token addresses as 20-byte values, and the inline comments even claim addresses are padded to 32 bytes. However, `Well.sol` locates subsequent data with `LOC_VARIABLE + numberOfTokens() * ONE_WORD` where `ONE_WORD == 32`. For any Well with more than one token (and even for one token, because the well-function data start is 12 bytes off), the token addresses, well-function address, well-function data, and pump data are read from the wrong immutable-arg offsets.
- Impact: Any Well deployed through the provided constructor libraries will read the wrong token addresses, well function, and pumps. Swaps, liquidity operations, and pump updates will operate on garbage configuration and will either revert or transfer the wrong tokens, causing loss of funds.

## `WellUpgradeable` initialization is front-runnable
- Location: `src/WellUpgradeable.sol` : `init`, `initNoWellToken`
- Mechanism: `LibWellUpgradeableConstructor` deploys a Well with `initFunctionCall = initNoWellToken()`, which only bumps the initializer version to 1 and leaves the ERC20 name/symbol and `Ownable` owner unset. The real `init(string,string)` is a public `reinitializer(2)` with no access control, so it can be called by anyone once `initNoWellToken` has run.
- Impact: An attacker can watch the deployment transaction and call `init` first, setting themselves as the Well owner and choosing arbitrary token metadata. If any owner-gated functionality is added later, the attacker controls it.

## `WellUpgradeable` UUPS upgrade authorization is broken
- Location: `src/WellUpgradeable.sol` : `_authorizeUpgrade`, `upgradeTo`, `upgradeToAndCall`, `proxiableUUID`
- Mechanism: `_authorizeUpgrade` validates the current proxy by reading `IAquifer(aquifer).wellImplementation(_getImplementation())`. Wells are deployed as EIP-1167 minimal clones, so `_getImplementation()` reads the unused ERC-1967 slot and returns `address(0)`, making the `activeProxy == ___self` check fail every time. Even if that check passed, the new-implementation validation only requires `wellImplementation(newImplementation) != 0`, which is true for any registered Well *proxy* rather than for a proper implementation contract.
- Impact: Legitimate upgrades are bricked because the authorization always reverts. The validation logic also treats registered proxy addresses as valid implementations, so if the primary check were ever satisfied an attacker could upgrade a Well to a malicious proxy and run arbitrary logic in the Well’s context.

## `MultiFlowPump` oracles become stale after the first update
- Location: `src/pumps/MultiFlowPump.sol` : `update` → `_capReserves`; `src/Well.sol` : `getReserves`, `_updatePumps`
- Mechanism: `MultiFlowPump._capReserves` calls `IWell(well).getReserves()` to read current reserves, but `Well.getReserves()` is protected by `readOnlyNonReentrant`. Every state-changing Well function is `nonReentrant`, so when the pump is invoked from `Well._updatePumps` the Well’s reentrancy status is already `_ENTERED` and `getReserves()` reverts. `Well._updatePumps` wraps the pump call in `try/catch` and silently ignores the failure.
- Impact: After the initial `_init` call, every subsequent pump update fails silently. The EMA and cumulative reserve oracles are never refreshed, so they report stale prices even as the Well’s real reserves change. Downstream protocols relying on these oracles can be manipulated or priced incorrectly.
