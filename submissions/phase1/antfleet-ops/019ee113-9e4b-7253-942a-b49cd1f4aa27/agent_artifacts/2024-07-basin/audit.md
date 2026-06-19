# Audit: 2024-07-basin

# Security Audit Report

## Stable2 `decodeWellData` - Wrong default for second decimal
- **Location:** `src/functions/Stable2.sol` : `decodeWellData`
- **Mechanism:** The function checks `if (decimal0 == 0) { decimal0 = 18; }` twice instead of checking `decimal1`. The second guard incorrectly tests `decimal0` again, so when `decimal1 == 0` (and `decimal0 != 0`), `decimal1` is never set to the default 18. `getScaledReserves` then computes `scaledReserves[1] = reserves[1] * 10 ** (18 - 0) = reserves[1] * 1e18`, massively over-scaling token 1 and causing arithmetic overflow / divergent iterations in `calcLpTokenSupply`, `calcReserve`, and the LUT-based ratio solvers.
- **Impact:** A Stable2 Well configured with `data = abi.encode(18, 0)` (or any 0 second-decimal) becomes immediately broken (DoS) on every price-sensitive function, and can return wildly incorrect reserve values leading to mispriced swaps, imbalanced liquidity, and oracle manipulation.

## WellUpgradeable `init` - Permissionless ownership takeover
- **Location:** `src/WellUpgradeable.sol` : `init`
- **Mechanism:** `init` is `external` with `reinitializer(2)` and **no access control**, and internally calls `__Ownable_init()` which sets `owner = msg.sender`. After a clone is bored by the Aquifer with `initNoWellToken` (version 1), the `init` function (version 2) can be called by *any* account to set the LP token metadata *and* become the contract owner. The intended deployer/admin is never granted any privileged role during boring; the owner is only established when `init` is invoked.
- **Impact:** An attacker can front-run the legitimate deployer's `init` call (or simply call it first), becoming the owner of the Well. The attacker can then (a) set a malicious ERC20 name/symbol for the LP token, and (b) exercise owner-only paths (notably `_authorizeUpgrade` / `upgradeTo`) on the Well — effectively hijacking the Well.

## WellUpgradeable - UUPS upgrade flow is incompatible with EIP-1167 boring
- **Location:** `src/WellUpgradeable.sol` : `_authorizeUpgrade`, `proxiableUUID`
- **Mechanism:** Wells are deployed by `Aquifer.boreWell` as **EIP-1167 minimal clones** (immutable args), not ERC-1967/UUPS proxies. `_authorizeUpgrade` calls `IAquifer(aquifer).wellImplementation(_getImplementation())` and requires the result to equal `___self`. `_getImplementation()` reads the ERC-1967 implementation slot, which is *always 0* for EIP-1167 clones, so `wellImplementation(0)` returns `address(0)` and the `require` always reverts. Additionally, even if that check passed, `_upgradeToAndCallUUPS` only writes the ERC-1967 slot, which has no effect on an EIP-1167 proxy whose implementation is hard-coded in its bytecode. The same problem defeats the `proxiableUUID` cross-check: when `newImplmentation` is the raw `WellUpgradeable` implementation contract, the `notDelegatedOrIsMinimalProxy` modifier sees `address(this) == ___self` and reverts; when it is a clone, the same modifier passes only because the clone was bored by the Aquifer, but the ERC-1967 slot is still never read by anything meaningful.
- **Impact:** The `upgradeTo` and `upgradeToAndCall` functions are non-functional — every upgrade attempt reverts. Combined with the previous finding, the only "owner" of a WellUpgradeable is the attacker who front-ran `init`, yet they (and any subsequent legitimate owner) cannot actually upgrade the Well, leaving the system in an inconsistent state where ownership is meaningful on paper but the advertised upgradeability is illusory.

## Well `_getIJ` - Allows `fromToken == toToken`
- **Location:** `src/Well.sol` : `_getIJ`
- **Mechanism:** `_getIJ` returns `(i, j)` for the two tokens, but performs no check that `iToken != jToken`. When a caller passes the same token for both `fromToken` and `toToken`, the function returns `i == j`. In `_swapFrom` this causes `reserves[i] += amountIn` followed by `reserves[j] = _calcReserve(...)` to overwrite the same slot, and `amountOut = reserveJBefore - reserves[j]` to be computed against the Well's invariant — effectively letting the caller redeem a portion of the invariant-mandated balance of that token for "free" or, combined with the `_setReserves` balance check, to force a revert that nonetheless leaves the pool in an unexpected state.
- **Impact:** Self-swaps can drain value from the pool or be used as a griefing/DoS vector. Any user-supplied swap path that accidentally (or maliciously) repeats a token can break the pool's accounting or extract tokens at the Well function's expense.

## Well `init` - No minimum token count
- **Location:** `src/Well.sol` : `init`
- **Mechanism:** `init` checks for duplicate tokens but never verifies `numberOfTokens() > 0` (or any sensible minimum). A Well can be bored with an empty tokens array, after which `tokens()` returns an empty array, `_getReserves(0)` returns an empty array, and every operation either silently no-ops or, in the case of `_addLiquidity` / `_swapFrom`, computes an LP supply change against an empty `reserves` array with undefined behavior in the Well function.
- **Impact:** A misconfigured (or maliciously configured) Well with zero tokens can be created, locking any value sent to it in the broken invariant math and producing nonsensical LP tokens or revert storms on every interaction.
