# Audit: 2024-07-basin

## Unrestricted upgrade of proxy-backed `WellUpgradeable` pools
- Location: [WellUpgradeable.sol](/Users/augstar/open-evmbench/audit_sources/2024-07-basin/src/WellUpgradeable.sol:65) : `_authorizeUpgrade`, [WellUpgradeable.sol](/Users/augstar/open-evmbench/audit_sources/2024-07-basin/src/WellUpgradeable.sol:93) : `upgradeTo`, [WellUpgradeable.sol](/Users/augstar/open-evmbench/audit_sources/2024-07-basin/src/WellUpgradeable.sol:104) : `upgradeToAndCall`
- Mechanism: The upgrade path never checks `msg.sender`. `_authorizeUpgrade` only verifies that the current implementation and the new implementation are Aquifer-registered and that the target reports the right `proxiableUUID`; it does not enforce `onlyOwner` even though the contract inherits `OwnableUpgradeable`. In the repo’s intended deployment pattern, an `ERC1967Proxy` points at a bored `WellUpgradeable`, so `_getImplementation()` resolves to the current bored Well and these checks succeed for any caller. Because `Aquifer.boreWell` is permissionless, an attacker can deploy their own malicious UUPS-compatible Well implementation through the same Aquifer, then call `upgradeTo` or `upgradeToAndCall` on the live proxy and pass authorization.
- Impact: Any externally owned account can take over an upgradeable Well proxy, replace its logic with attacker-controlled code, and then drain reserves, mint/burn LP arbitrarily, or permanently brick the pool.

## Stable2 misdecodes the second token’s `0 => 18` decimals sentinel
- Location: [Stable2.sol](/Users/augstar/open-evmbench/audit_sources/2024-07-basin/src/functions/Stable2.sol:310) : `decodeWellData`
- Mechanism: `decodeWellData` is supposed to treat a stored decimal value of `0` as “assume 18 decimals” for both tokens. It correctly fixes `decimal0`, but the second guard mistakenly re-checks `decimal0` instead of `decimal1`. As a result, whenever the second token is encoded with the documented sentinel `0`, `decimal1` remains `0`. All Stable2 math then scales reserve 1 by `10**18` in `getScaledReserves`, corrupting `calcLpTokenSupply`, `calcReserve`, `calcRate`, and the swap/liquidity solvers.
- Impact: Any Stable2 Well deployed with `decimal1 == 0` is fundamentally mispriced. Traders can extract value through grossly favorable swaps, and LP accounting becomes wrong enough to let users add or remove liquidity at distorted ratios, causing direct loss to counterparties and LPs.

I did not identify additional concrete exploit paths in the provided scope beyond those two.

