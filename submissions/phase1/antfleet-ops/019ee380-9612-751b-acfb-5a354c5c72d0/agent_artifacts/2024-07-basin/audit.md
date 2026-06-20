# Audit: 2024-07-basin

Below are the genuine security vulnerabilities I found. I focused on logic/access-control/accounting flaws with concrete exploit paths.

## Missing authorization on Well upgrades
- Location: `src/WellUpgradeable.sol` : `_authorizeUpgrade` / `upgradeTo` / `upgradeToAndCall`
- Mechanism: `WellUpgradeable` inherits `OwnableUpgradeable` and calls `__Ownable_init()` in `init`, but the overridden `_authorizeUpgrade` contains **no `onlyOwner` (or any caller-identity) check**. It only verifies (a) the call is via delegatecall, (b) the executing proxy was bored by the aquifer, and (c) `newImplementation` is some address registered in `aquifer.wellImplementation(...)` with a valid `proxiableUUID`. None of these conditions bind the *caller*. Because `upgradeTo`/`upgradeToAndCall` are `public` and route straight into `_authorizeUpgrade`, any externally-owned account can call them.
- Impact: Any unprivileged user can upgrade a victim's `WellUpgradeable` proxy. An attacker can permissionlessly bore their own `WellUpgradeable` implementation through the (permissionless) Aquifer so it becomes a registered key in the `wellImplementation` mapping, satisfy the `proxiableUUID` check, then call `upgradeToAndCall(maliciousImpl, initData)` on someone else's Well. This gives full control over the Well's logic and lets the attacker drain all pooled liquidity, or simply brick the Well. This is a complete loss-of-funds / takeover bug — the Ownable machinery is wired in but never enforced.

## Wrong variable in decimal defaulting corrupts Stable2 pricing
- Location: `src/functions/Stable2.sol` : `decodeWellData`
- Mechanism: The defaulting logic has a copy-paste error:
  ```solidity
  if (decimal0 == 0) { decimal0 = 18; }
  if (decimal0 == 0) { decimal1 = 18; }   // should test decimal1
  ```
  The second `if` re-tests `decimal0` (which was just forced non-zero) instead of `decimal1`. Consequently `decimal1` is never defaulted to 18 when it is encoded as 0. `getScaledReserves` then computes `reserves[1] * 10**(18 - 0) = reserves[1] * 1e18`, scaling token-1's reserve by 18 extra orders of magnitude rather than treating it as an 18-decimal token.
- Impact: For any Stable2 Well whose token-1 uses the `0`-means-18 sentinel, `calcLpTokenSupply`, `calcReserve`, and `calcRate` operate on a grossly mis-scaled reserve. This corrupts swap amounts and LP accounting (massively overvaluing one side), and feeds a wrong `calcRate` into the MultiFlow oracle. An arbitrageur can systematically extract value from / imbalance such a pool, and the manipulation-resistant oracle reports incorrect prices.

## ConstantProduct.calcReserve rounds down, violating the round-up invariant
- Location: `src/functions/ConstantProduct.sol` : `calcReserve`
- Mechanism: `IWellFunction.calcReserve` is explicitly documented to round **up** ("Well reserves are marginally higher to enforce `calcLpTokenSupply(...) >= totalSupply()`"), and the 2-token variant `ConstantProduct2.calcReserve` correctly uses `LibMath.roundUpDiv`. The N-token `ConstantProduct.calcReserve` instead uses plain integer division:
  ```solidity
  reserve = (lpTokenSupply / n) ** n;
  for (...) if (i != j) reserve = reserve / reserves[i];
  ```
  which rounds the solved reserve *down*. In `Well._swapFrom`, `amountOut = reserveJBefore - reserves[j]`; a reserve `j` computed too low yields an `amountOut` biased in the user's favor on every swap.
- Impact: Each swap/withdrawal against an N-token ConstantProduct Well leaks a rounding amount to the caller at the pool's expense and can let the post-trade invariant fall below `totalSupply()`. The leakage is small per call but is directionally consistent and repeatable, allowing gradual extraction of pooled funds; it also breaks the stated `calcLpTokenSupply >= totalSupply` guarantee other code relies on.

I did not find exploitable reentrancy (all state-changing externals are `nonReentrant` and follow checks-effects with `_setReserves`' balance validation), and the FoT handling / `skim`/`sync` excess-extraction behavior is intentional per the documented design.

