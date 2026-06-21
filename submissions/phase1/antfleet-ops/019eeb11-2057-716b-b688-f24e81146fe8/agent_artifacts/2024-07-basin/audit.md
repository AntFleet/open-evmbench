# Audit: 2024-07-basin
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

I merged the 6 reports (3 × claude-opus-4-8, 3 × gpt-5.5). Across all inputs there are 20 finding-instances collapsing to **7 distinct findings** (by code path + root cause). All 7 appear below.

---

## Consensus findings

## Unauthenticated UUPS upgrade authorization
*(consensus, 6 of 6 reports)*
- Location: `src/WellUpgradeable.sol` : `_authorizeUpgrade` / `upgradeTo` / `upgradeToAndCall`
- Mechanism: `_authorizeUpgrade` performs only structural checks — that the call runs in delegatecall/proxy context, that `newImplementation` is registered in the Aquifer's `wellImplementation` mapping, and that `proxiableUUID() == _IMPLEMENTATION_SLOT` — and never checks `msg.sender`/`onlyOwner`. The overridden `upgradeTo`/`upgradeToAndCall` also drop OZ's guards. `OwnableUpgradeable` is inherited and `__Ownable_init()` runs, but `onlyOwner` is never enforced anywhere. Because `Aquifer.boreWell` is permissionless, an attacker bores their own malicious implementation that satisfies the registry/`proxiableUUID` checks.
- Impact: Any external account can upgrade any `WellUpgradeable` proxy to attacker-controlled logic and execute arbitrary code in the Well's storage context — drain all reserves, rewrite ownership, or brick the Well. Complete takeover, unprivileged.
- Reviewer disagreement: none.

## Stable2 `decodeWellData` decimal-default typo (token1 never defaults to 18)
*(consensus, 6 of 6 reports)*
- Location: `src/functions/Stable2.sol` : `decodeWellData` (feeding `getScaledReserves`)
- Mechanism: Copy-paste typo — the second guard re-tests `decimal0` instead of `decimal1`:
  ```solidity
  if (decimal0 == 0) { decimal0 = 18; }
  if (decimal0 == 0) { decimal1 = 18; }   // always false; should test decimal1
  ```
  After the first block `decimal0` is non-zero, so `decimal1` is never defaulted from the documented `0 ⇒ 18` sentinel; `decimals[1]` stays `0`. The `decimal1 > 18` bound passes for `0`, so deployment succeeds, and `getScaledReserves` computes `reserves[1] * 10**(18 - 0) = reserves[1] * 1e18`.
- Impact: Any Stable2 Well relying on the zero-default for token1 (e.g. `abi.encode(6, 0)` or `abi.encode(0,0)`) is catastrophically mispriced; the StableSwap invariant, `calcReserve`, `calcLpTokenSupply`, and `calcRate` all see token1 inflated by ~1e18. An attacker swaps dust of token0 to drain token1 (or mints outsized LP), and the corrupted `calcRate` poisons the Beanstalk deltaB oracle. Misconfiguration is immutable once bored.
- Reviewer disagreement: none.

## Front-runnable unprotected reinitializer grants Well ownership
*(consensus, 3 of 6 reports)*
- Location: `src/WellUpgradeable.sol` : `init` (`reinitializer(2)`) / `initNoWellToken` (`initializer`), with `src/libraries/LibWellUpgradeableConstructor.sol` : `encodeWellDeploymentData`
- Mechanism: Upgradeable Wells are bored with `initData = initNoWellToken()`, which only consumes initializer version 1 and does not set name/symbol or call `__Ownable_init`. The owner-establishing `init(name, symbol)` is a separate `reinitializer(2)` call with no caller restriction; it runs `__Ownable_init()`, setting `owner = msg.sender`. Because the bore does not call `init` atomically, the first arbitrary caller after deployment becomes owner.
- Impact: An attacker front-runs the legitimate post-deployment `init` to seize ownership of the Well (and set name/symbol). Combined with any owner-gated logic — or once the upgrade-auth finding above is fixed — this is the alternate path to full upgrade/drainage control.
- Reviewer disagreement: none.

## ConstantProduct `calcReserve` rounds down, overpaying traders
*(consensus, 2 of 6 reports)*
- Location: `src/functions/ConstantProduct.sol` : `calcReserve`
- Mechanism: `calcReserve` computes `(lpTokenSupply / n) ** n` and then repeatedly truncating-divides by the other reserves, rounding the required post-trade reserve **down** even though `IWellFunction.calcReserve` requires rounding **up** so the Well retains enough reserves. In small or low-decimal pools it can even return `0` for a positive mathematical reserve.
- Impact: In `swapFrom`/`swapTo`/`removeLiquidityOneToken` (output computed as `oldReserve - calcReserve`), a trader receives more than the invariant allows; a 3-token ConstantProduct Well with small integer reserves can have an entire token reserve drained. The two-token `ConstantProduct2` fast path is unaffected.
- Reviewer disagreement: all three claude-opus-4-8 shots examined the constant-product math and asserted its rounding "consistently favors the Well" / is sound (3 of 6 reports defended this code path).

---

## Minority findings

## `LibBytes.storeUint128` corrupts the last reserve for odd-length reserve arrays
*(minority, 1 of 6 reports)* *(conflicting reviews: 2 of 6 reports defended this code path)*
- Location: `src/libraries/LibBytes.sol` : `storeUint128` (the `reserves.length & 1 == 1` branch)
- Mechanism: For an odd reserve count the final reserve is packed alone in the low 128 bits. The write is `sstore(add(slot, maxI), add(mload(...lastReserve), shr(128, shl(128, sload(add(slot, maxI))))))`. `shr(128, shl(128, x))` keeps the **low** 128 bits of the existing slot (the previous value of this same reserve) and adds the new reserve, so the stored value becomes `newReserve + oldReserve (mod 2^128)`. To replace the low half while preserving the unused upper half it must be `shl(128, shr(128, x))`. `readUint128` reads back only the low 128 bits.
- Impact: The first write is correct (old value 0), but every subsequent write to any odd-token Well (n ≥ 3 — e.g. a 3-token ConstantProduct Well the permissionless Aquifer will deploy) accumulates/wraps the last reserve and reads back wrong. Reserves desynchronize from balances → mispriced swaps/liquidity, `InvalidReserves` reverts (DoS), drift is attacker-directable via ordinary swaps. The dedicated two-reserve fast path is correct, so 2-token Wells are unaffected.
- Reviewer disagreement: claude-opus-4-8 shots 1 and 3 reviewed the reserve byte-packing / `storeUint128` and deemed it sound ("guards against >uint128 with `require`, no silent downcast"), without flagging the odd-length accumulation.

## Stable2 `calcReserve` scale-back floors in the caller's favor
*(minority, 1 of 6 reports)* *(conflicting reviews: 3 of 6 reports defended this code path)*
- Location: `src/functions/Stable2.sol` : `calcReserve`
- Mechanism: After Newton iteration in 18-decimal scaled units, `calcReserve` converts back to the token's native decimals with floor division: `reserve / (10 ** (18 - decimals[j]))`. For swap and single-token-withdrawal paths the required reserve should be rounded **up**; flooring understates it by up to one native token unit.
- Impact: Callers of `swapFrom`, `swapTo`, or `removeLiquidityOneToken` receive too much output or underpay input due to favorable rounding, and can repeat/split operations to accumulate the error. Most material for low-decimal tokens where one native unit is economically meaningful.
- Reviewer disagreement: claude-opus-4-8 shot 3 explicitly defended this path — "the only Stable2 rounding imprecision (±1 in `calcReserve` rounding down on scale-back) is bounded to sub-unit dust and is documented, not a profitable exploit"; shots 1–2 likewise asserted every imprecise division is biased toward the Well.

## Duplicate tokens allowed in upgradeable Wells via `initNoWellToken`
*(minority, 1 of 6 reports)*
- Location: `src/WellUpgradeable.sol` : `initNoWellToken` ; `src/Well.sol` : `_getIJ` / swap paths
- Mechanism: `Well.init` and `WellUpgradeable.init` reject duplicate tokens, but `initNoWellToken` marks an upgradeable Well initialized **without** running that duplicate-token invariant check. With duplicate token entries, `_getIJ` can resolve the same ERC20 as two different reserve indices, so swap math treats one real token balance as two virtual reserves.
- Impact: A duplicate-token upgradeable Well can be drained once it holds liquidity: an attacker calls same-token swap paths such as `swapFrom(token, token, ...)` and extracts more of the same ERC20 than deposited whenever the virtual reserves are imbalanced. Precondition: the Well was initialized via `initNoWellToken` with duplicate token addresses.
- Reviewer disagreement: none (no other report addressed `initNoWellToken`'s missing duplicate-token check).

---

**Checklist:** distinct input findings (by code path + root cause) = 7; findings emitted = 7. No drops, no merges across differing code paths or root causes (ConstantProduct `calcReserve` and Stable2 `calcReserve` are kept separate as different code paths; the upgrade-auth and reinitializer findings are kept separate as different root causes).

