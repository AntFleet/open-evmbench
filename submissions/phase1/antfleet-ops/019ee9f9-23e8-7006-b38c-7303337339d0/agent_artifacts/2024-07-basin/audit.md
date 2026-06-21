# Audit: 2024-07-basin

# Basin Protocol Security Audit Report

## Stable2 `decodeWellData` fails to default `decimal1` to 18

- Location: `src/functions/Stable2.sol` : `decodeWellData`
- Mechanism: The function is intended to treat a `0` value in well data as “use 18 decimals” for each token. The second defaulting branch checks `decimal0 == 0` again instead of `decimal1 == 0`. As a result, whenever `decimal1` is encoded as `0` (including the common `(0, 0)` encoding where both tokens should default to 18), `decimal1` remains `0`. `getScaledReserves` then scales token-1 reserves with `10 ** (18 - 0)`, massively mis-scaling reserves and corrupting every Stable2 pricing path (`calcLpTokenSupply`, `calcReserve`, `calcRate`, swaps, liquidity math).
- Impact: A Stable2 Well deployed with `decimal1 = 0` in its well-function data will quote swaps and liquidity operations at severely wrong prices. An attacker can trade against the mispriced curve and extract value from LPs, or grief deployment of such Wells.

---

## Stable2 ratio solvers silently return zero on non-convergence

- Location: `src/functions/Stable2.sol` : `calcReserveAtRatioSwap`, `calcReserveAtRatioLiquidity`
- Mechanism: Both functions iterate up to 255 times to converge on a target price, but unlike `calcReserve` they do not revert if convergence fails. On failure they fall through and return the default `uint256` value `0`. `MultiFlowPump` calls these via `calcReservesAtRatioSwap` / `tryCalcReserveAtRatioSwap` and then clamps with `Math.max(..., 1)`, so a failed solve is treated as a ~1-wei reserve rather than an error.
- Impact: When Newton’s method fails (e.g., extreme ratios, edge-case reserves, or LUT boundaries), `MultiFlowPump` rate/LP caps can be computed against near-zero reserves while real Well reserves are much larger. An attacker who moves reserves into such a state can weaken or bypass pump capping and manipulate EMA/cumulative/TWA oracle readings that downstream systems (e.g., Beanstalk) rely on for pricing and solvency checks.

---

## Permissionless `init()` on `WellUpgradeable` lets anyone seize ownership

- Location: `src/WellUpgradeable.sol` : `init`
- Mechanism: `LibWellUpgradeableConstructor` deploys Wells with `initNoWellToken()` (`initializer`, version 1) as the only init call in `boreWell`. Full setup is deferred to `init(string,string)`, which is a `reinitializer(2)` callable by anyone once version 1 is set. `init()` calls `__Ownable_init()`, which sets `owner = msg.sender` with no access control on who may call `init`.
- Impact: After a `WellUpgradeable` is bored, any account can front-run the deployer’s `init()` transaction and become `owner` of the Well. While the current code does not expose `onlyOwner` fund-moving functions, ownership is a privileged role (upgrade path, future owner-gated logic, off-chain trust assumptions). A deployer can lose control of their Well immediately after deployment.

---

## `WellUpgradeable._authorizeUpgrade` queries the Aquifer mapping with the wrong key

- Location: `src/WellUpgradeable.sol` : `_authorizeUpgrade`
- Mechanism: Upgrade authorization verifies the caller with `IAquifer(aquifer).wellImplementation(_getImplementation())`, but Aquifer’s mapping is `well → implementation`, not `implementation → well`. The same contract correctly uses `wellImplementation(address(this))` in `notDelegatedOrIsMinimalProxy`. On ERC-1167 clones bored by Aquifer, `_getImplementation()` reads the ERC-1967 implementation slot, which is never populated (the implementation is embedded in clone bytecode), so the lookup is against `address(0)` and the check fails. The intended check should use `address(this)` (the bored Well clone).
- Impact: Upgrade authorization is inconsistent with the rest of the contract and does not correctly bind upgrades to Aquifer-registered Wells. On standard Aquifer-bored clones, legitimate upgrades are blocked. In other deployment contexts where the ERC-1967 slot is populated, the check could validate against an unrelated registry entry, undermining the stated security model that only Aquifer-bored active proxies may upgrade.

---

## `MultiFlowPump._init` can permanently skip oracle initialization

- Location: `src/pumps/MultiFlowPump.sol` : `_init`
- Mechanism: On a Well’s first pump update, if any reserve in the array is `0`, `_init` returns early without writing `lastTimestamp`, EMA, or cumulative state. The outer `update` path treats `lastTimestamp == 0` as “never initialized” and keeps re-entering `_init` on every subsequent update until all reserves are simultaneously non-zero.
- Impact: For a newly created or partially drained Well where one side of the pair is zero, the pump never initializes and all oracle read functions (`readLastCappedReserves`, `readInstantaneousReserves`, `readCumulativeReserves`, `readTwaReserves`) revert with `NotInitialized`. An attacker can grief oracle availability by keeping one reserve at zero (or deploying into that state), breaking integrations that depend on pump prices until both reserves are nonzero in the same update.

