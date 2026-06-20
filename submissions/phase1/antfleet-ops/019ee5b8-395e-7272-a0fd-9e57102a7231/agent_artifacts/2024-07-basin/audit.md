# Audit: 2024-07-basin

## Anyone can upgrade a WellUpgradeable proxy
- Location: `src/WellUpgradeable.sol` : `_authorizeUpgrade`, `upgradeTo`, `upgradeToAndCall`
- Mechanism: `upgradeTo` and `upgradeToAndCall` are public, and `_authorizeUpgrade` never checks `msg.sender`, `onlyOwner`, or any authorized upgrader role. Its checks only prove that the call is through the expected proxy/clone structure and that the new implementation is an Aquifer-registered Well with a valid `proxiableUUID`. Because `Aquifer.boreWell` is permissionless, an attacker can register a malicious compatible implementation/clone and then call `upgradeTo` or `upgradeToAndCall` on a victim WellUpgradeable proxy.
- Impact: Any account can replace a victim WellUpgradeable’s logic with attacker-controlled code, then drain the tokens held by the Well or permanently brick it.

## Stable2 misdecodes token1 decimals
- Location: `src/functions/Stable2.sol` : `decodeWellData`
- Mechanism: `decodeWellData` intends to treat a decoded decimal value of `0` as “18 decimals”, but the second check repeats `decimal0 == 0` instead of checking `decimal1 == 0`. As a result, when token1 is encoded with the documented zero sentinel, `decimal1` remains `0`. All Stable2 math then scales token1 reserves by `10 ** (18 - 0)`, inflating that side of the invariant by `1e18`.
- Impact: Stable2 Wells using `0` for token1’s 18-decimal sentinel are severely mispriced. Swaps, liquidity minting, withdrawals, and oracle rate calculations can use corrupted reserves, allowing value extraction from LPs or causing pool operations to revert/brick.

