# Audit: 2024-07-basin

## Missing authorization on upgradeable Well upgrades
- Location: `src/WellUpgradeable.sol` : `_authorizeUpgrade`, `upgradeTo`, `upgradeToAndCall`
- Mechanism: `upgradeTo` and `upgradeToAndCall` are public, and `_authorizeUpgrade` never checks `onlyOwner` or any caller authorization. It only checks that the current/new implementations fit the Aquifer/UUPS shape. In the intended proxy-backed pattern, those checks are independent of `msg.sender`; because Aquifer registration is permissionless, an attacker can register a compatible malicious Well implementation and pass the checks.
- Impact: Any account can upgrade a victim upgradeable Well proxy to attacker-controlled logic and drain pooled tokens, mint/burn LP arbitrarily, or brick the proxy.

## Public reinitializer can reopen reentrancy during an active call
- Location: `src/WellUpgradeable.sol` : `init`, `initNoWellToken`
- Mechanism: Upgradeable Wells bored through `LibWellUpgradeableConstructor.encodeWellDeploymentData` are initialized only with `initNoWellToken()`, leaving `init(string,string)` callable once as `reinitializer(2)`. `init` calls `__ReentrancyGuard_init()`, which resets the guard status. During a callback-capable token transfer inside a `nonReentrant` Well operation, an attacker can call `init`, reset the guard while the outer operation is still running, and reenter functions such as `sync` against stale reserves before the outer call finishes accounting.
- Impact: For affected direct `WellUpgradeable` clones, an attacker can bypass the reentrancy guard once and double-count the same transferred tokens, minting LP or executing nested liquidity/swap flows before reserves are updated.

## Stable2 mis-scales the second token when decimals are encoded as zero
- Location: `src/functions/Stable2.sol` : `decodeWellData`
- Mechanism: `decodeWellData` intends to treat `0` decimals as “default to 18” for both tokens, but the second condition checks `decimal0 == 0` again instead of `decimal1 == 0`. As a result, `decimal1` remains `0` when encoded as the documented sentinel, and `getScaledReserves` multiplies reserve 1 by `10 ** 18` instead of leaving an 18-decimal token unscaled.
- Impact: Any Stable2 Well configured with `decimal1 == 0` has a corrupted invariant and oracle rate. Swaps and liquidity operations are priced off reserves inflated by 18 orders of magnitude, allowing arbitrageurs to extract value from LPs.

## Two-token Well functions ignore extra reserves
- Location: `src/Well.sol` : `removeLiquidityImbalanced`; `src/functions/ConstantProduct2.sol` : `calcLpTokenSupply`; `src/functions/Stable2.sol` : `calcLpTokenSupply`
- Mechanism: `Well.init` does not enforce that two-token Well functions are only paired with exactly two tokens. `ConstantProduct2` and `Stable2` compute LP supply from only `reserves[0]` and `reserves[1]`. In a Well configured with three or more tokens, `removeLiquidityImbalanced` transfers all requested token amounts first, then computes `lpAmountIn`; withdrawing only token index `>= 2` leaves the LP supply unchanged, so `lpAmountIn` is zero.
- Impact: In any such misconfigured Well, an attacker can withdraw all ignored extra-token reserves through `removeLiquidityImbalanced` while burning zero LP.

## ConstantProduct reserve solving rounds in favor of traders
- Location: `src/functions/ConstantProduct.sol` : `calcReserve`
- Mechanism: `IWellFunction.calcReserve` requires rounding up so the post-operation reserve is not understated. The N-token `ConstantProduct` implementation uses plain integer division in a loop, which rounds down. `Well._swapFrom` and one-sided liquidity removal then compute output as `oldReserve - roundedDownReserve`, overpaying the caller.
- Impact: Attackers can repeatedly trade or remove one-sided liquidity from N-token ConstantProduct Wells to extract the rounding surplus from LP reserves and violate the intended invariant.

## Final one-sided exit leaves remaining reserves stealable
- Location: `src/Well.sol` : `removeLiquidityOneToken`, `removeLiquidityImbalanced`, `shift`
- Mechanism: A user can burn the entire LP supply while withdrawing only one token. The selected reserve is reduced, but other reserves remain stored while `totalSupply()` becomes zero. For the provided Well functions, solving a reserve at zero LP supply returns zero, so a later `shift` treats the remaining balances as extractable output.
- Impact: If the final LP exits one-sided, any account can call `shift` afterward and steal the remaining token reserves left in the Well.

