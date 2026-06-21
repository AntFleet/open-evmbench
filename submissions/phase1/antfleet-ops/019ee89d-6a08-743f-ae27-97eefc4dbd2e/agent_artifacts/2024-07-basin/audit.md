# Audit: 2024-07-basin

## Missing owner authorization in UUPS upgrade path
- Location: src/WellUpgradeable.sol : `_authorizeUpgrade` (reached via `upgradeTo` / `upgradeToAndCall`)
- Mechanism: `WellUpgradeable` inherits `OwnableUpgradeable` and calls `__Ownable_init()`, but `_authorizeUpgrade` performs no caller check whatsoever — it never compares `msg.sender` to `owner()`. Its only gates are that the call is delegated through a proxy whose current ERC1967 implementation maps to `___self` in the Aquifer registry, that `IAquifer.wellImplementation(newImplmentation) != address(0)`, and that `newImplmentation.proxiableUUID() == _IMPLEMENTATION_SLOT`. Because the Aquifer is a permissionless factory, an attacker can `boreWell` their own malicious well (pointing at attacker logic that returns the correct `aquifer()`/`proxiableUUID`) to satisfy those registry checks, then call the public, unguarded `upgradeTo(maliciousWell)` on any victim `WellUpgradeable` proxy. Nothing restricts the caller to the Well’s owner, so the standard UUPS access control (which belongs in `_authorizeUpgrade`) is absent.
- Impact: Any account can replace the logic of any `WellUpgradeable` proxy with attacker-controlled code and drain all tokens and LP held by that Well.

## Tail-slot reserve write accumulates instead of overwriting
- Location: src/libraries/LibBytes.sol : `storeUint128`
- Mechanism: For an odd number of reserves the final reserve is written alone to `slot+maxI` as `add(newReserve, shr(128, shl(128, sload(slot+maxI))))`. `shr(128, shl(128, x))` isolates the *low* 128 bits of the existing slot — the exact location where this reserve’s previous value lives (uint128 reserves are right-aligned, and `readUint128` reads this tail from the low 128 bits). The mask is inverted: preserving the unused high bits would require `shl(128, shr(128, x))`. As written, every update after the first adds the new reserve to the stale stored reserve (e.g. storing `7` over a stored `5` yields `12`). The full-slot loop overwrites correctly, so only the tail reserve of an odd-length array is corrupted; 2-token Wells take the `length == 2` shortcut and are unaffected.
- Impact: Any Well with an odd number of tokens (n ≥ 3, e.g. an N-token `ConstantProduct` Well) corrupts its last reserve on every operation after the first, breaking swap/liquidity accounting and enabling reserve inflation, fund loss, or denial of service.

## `decodeWellData` never applies the 18-decimal default to the second token
- Location: src/functions/Stable2.sol : `decodeWellData`
- Mechanism: The function is meant to treat an encoded decimal of `0` as the default `18`. It does this for `decimal0`, but the second guard reads `if (decimal0 == 0) { decimal1 = 18; }` — a copy-paste of `decimal0` where `decimal1` was intended. Since the first guard guarantees `decimal0 != 0` afterward, this branch is dead and `decimal1` is never defaulted. A Well whose well-data encodes the second token’s decimals as `0` (the documented "assume 18" convention) keeps `decimals[1] = 0`, so `getScaledReserves` computes `reserves[1] * 10**(18 - 0) = reserves[1] * 1e18` instead of `* 1`, mis-scaling reserve 1 by a factor of 1e18 in every `calcReserve`, `calcLpTokenSupply`, and `calcRate` evaluation.
- Impact: Stableswap pricing for such a Well is grossly mis-scaled, letting an attacker arbitrage/swap against the corrupted curve to drain the pool.

## `ConstantProduct.calcReserve` rounds down instead of up
- Location: src/functions/ConstantProduct.sol : `calcReserve`
- Mechanism: `IWellFunction.calcReserve` is documented to round **up** so the invariant `calcLpTokenSupply(reserves) >= totalSupply()` is preserved (the 2-token variant uses `LibMath.roundUpDiv`). `ConstantProduct.calcReserve` instead computes `reserve = (lpTokenSupply / n) ** n` (truncating before exponentiation) and then `reserve = reserve / reserves[i]` with plain integer division, rounding **down** at every step. In `_swapFrom`, `swapTo`, and `removeLiquidityOneToken`, a smaller-than-true `reserve[j]` produces a larger `amountOut` (or smaller `amountIn`), so the rounding residue is paid out to the caller rather than retained by the Well.
- Impact: Each swap or single-sided withdrawal on an N-token `ConstantProduct` Well leaks a small amount of output token from LPs to the caller, a repeatable accounting drift in the user’s favor.

