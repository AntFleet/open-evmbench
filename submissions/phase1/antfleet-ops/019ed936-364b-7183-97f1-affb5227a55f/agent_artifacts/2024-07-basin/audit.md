# Audit: 2024-07-basin

Here is the merged report.

---

# Merged Security Audit — Beanstalk Wells

This report consolidates two independent audits (Reviewer A = Claude, Reviewer B = Codex) of the same codebase. Findings confirmed by both reviewers appear first as consensus; findings raised by only one reviewer follow. Each finding preserves its original location, mechanism, and impact, with the most specific description from either side retained.

## Consensus findings

### Stable2 misdecodes the token1 zero-decimals sentinel (`decimal1` is never defaulted)
*(consensus)*
- **Location:** `src/functions/Stable2.sol` : `decodeWellData` — the second guard in the defaulting block, immediately after `(uint256 decimal0, uint256 decimal1) = abi.decode(...)`.
- **Mechanism:** A stored decimal of `0` is meant as a sentinel for "assume 18 decimals." This is applied correctly to `decimal0`, but the second guard is a copy-paste error that re-tests `decimal0` instead of `decimal1`:
  ```solidity
  if (decimal0 == 0) { decimal0 = 18; }
  if (decimal0 == 0) { decimal1 = 18; }   // BUG: must be `if (decimal1 == 0)`
  ```
  Because the second condition re-tests `decimal0` (already set to 18, or non-zero), `decimal1` is never defaulted. When a Well's `data` encodes `decimal1 == 0` (e.g. `(18, 0)` or `(0, 0)`), `decimals[1]` stays `0`. Every Stable2 entry point (`calcLpTokenSupply`, `calcReserve`, `calcRate`, `calcReserveAtRatioSwap`, `calcReserveAtRatioLiquidity`) then calls `getScaledReserves`, which computes `scaledReserves[1] = reserves[1] * 10**(18 - 0) = reserves[1] * 1e18` instead of the intended `* 1`. Reserve index 1 is inflated by `1e18` inside the invariant solver while reserve 0 is scaled correctly, and `calcReserve` divides the result back down by `10**(18-0) = 1e18` on the wrong side. The StableSwap invariant is computed on corrupted reserves.
- **Impact:** Any Stable2 Well whose well-function `data` carries `decimal1 == 0` is mispriced by ~18 orders of magnitude on one side of the curve, valuing token1 at ~`1e-18` of its true price. Boring a Well is permissionless and `0 ⇒ 18` is the documented contract, so this is reachable two ways: (a) an honest deployer relies on the documented sentinel for the second token and unknowingly ships a broken Well; (b) an attacker deliberately bores a Stable2 Well with `data = abi.encode(18, 0)`. In either case `getSwapOut`/`swapFrom`, `addLiquidity`, and `removeLiquidity*` operate on the corrupted curve, letting an attacker swap in a negligible amount and drain the counter-token, or add/withdraw liquidity at grossly favorable ratios. Liquidity providers lose funds.

### Unauthorized UUPS upgrade authorization (`_authorizeUpgrade` lacks `onlyOwner`)
*(consensus)*
- **Location:** `src/WellUpgradeable.sol` : `_authorizeUpgrade`, `upgradeTo`, `upgradeToAndCall`.
- **Mechanism:** `upgradeTo` and `upgradeToAndCall` are public and `_authorizeUpgrade` does not enforce `onlyOwner` or any caller authorization. It only verifies that the current and new implementations are Aquifer-registered (via `_getImplementation()` / `proxiableUUID()`). Since Aquifer is permissionless, Reviewer B notes an attacker can register a malicious UUPS-compatible Well implementation that satisfies these checks. Reviewer A adds nuance: the check gates on Aquifer registration of `_getImplementation()`, and for a freshly cloned minimal proxy the ERC1967 implementation slot is unset, so that specific path reverts — but the missing ownership check on public `upgradeTo`/`upgradeToAndCall` remains a fragile design that should be hardened. (The two reviewers disagree on immediate exploitability for a fresh minimal proxy; both agree the missing `onlyOwner` is a real defect.)
- **Impact:** Any upgradeable Well proxy using this UUPS path can be upgraded by anyone to attacker-controlled logic, enabling theft of the Well's token balances or permanent bricking. Precondition: the target must be an upgradeable Well proxy using this UUPS path.

## Additional findings (single-reviewer)

### Upgradeable Well can be initialized (and its owner seized) by anyone after deployment
*(Reviewer A only)*
- **Location:** `src/WellUpgradeable.sol` : `init` (the `reinitializer(2)` function), in combination with `initNoWellToken` and `src/libraries/LibWellUpgradeableConstructor.sol` : `encodeWellDeploymentData`.
- **Mechanism:** Upgradeable Wells are deployed via `encodeWellDeploymentData`, whose `initData` is `initNoWellToken()`. `initNoWellToken` is an `initializer` that consumes initialized-version 1 and sets nothing (no owner, no ERC20 name/symbol). The Aquifer's post-deploy check `IWell(well).isInitialized()` passes because the version is now `> 0`, so deployment succeeds with the Well half-initialized. The real setup function `init(name, symbol)` is `reinitializer(2)`, still callable once because the version is `1 < 2`, and it runs `__Ownable_init()` (setting `owner = msg.sender`) plus `__ERC20_init` / `__ERC20Permit_init`. Nothing restricts `init`'s caller to the deployer or Aquifer, so it is a separate, front-runnable transaction.
- **Impact:** An attacker who observes or front-runs the deployer's `init` call can call `init` first, permanently consuming the `reinitializer(2)` slot. The attacker becomes the Well's `Ownable` owner and sets arbitrary ERC20 `name`/`symbol`; the legitimate deployer can never properly initialize the Well afterward. This is a permanent takeover/grief of the Well instance.

### Final one-sided withdrawal leaves reserves stealable
*(Reviewer B only)*
- **Location:** `src/Well.sol` : `removeLiquidityOneToken`, `removeLiquidityImbalanced`, `shift`.
- **Mechanism:** `removeLiquidityOneToken` and `removeLiquidityImbalanced` allow burning the entire LP supply while withdrawing only one side of the pool. They reduce only the requested reserve and leave the other reserves stored with `totalSupply() == 0`. For `ConstantProduct2`, `calcReserve(..., lpTokenSupply = 0)` returns zero, so a later `shift` treats the remaining reserve as extractable output.
- **Impact:** If the final LP exits one-sided, any account can back-run or later call `shift` to take the remaining token reserves. The exiting LP receives only the selected token while the other side can be stolen.

---

**Note on structure:** Section headers use `##` and individual findings use `###` to keep findings nested under their section; the per-finding schema (title / tag / Location / Mechanism / Impact) is otherwise preserved as specified. Reviewer A's main finding 2 was the front-runnable `init` reinitializer takeover (distinct from B's `_authorizeUpgrade` finding); A's parenthetical observation about the missing `onlyOwner` on `upgradeTo`/`upgradeToAndCall` is what makes the UUPS authorization issue a consensus finding rather than B-only.

