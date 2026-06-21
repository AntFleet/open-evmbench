# Audit: 2024-06-vultisig

Here is a security audit of the provided contracts, focused on exploitable logic flaws rather than style or centralization unless it creates a concrete attack path.

---

## ETH contribution cap bypass via underestimated oracle quotes

- **Location:** `Whitelist.sol` : `checkWhitelist`
- **Mechanism:** Pool buys debit `_contributed[to]` using `IOracle(_oracle).peek(amount)`, not the actual ETH/WETH spent in the swap. `UniswapV3Oracle.peek` intentionally returns a discounted TWAP estimate (`* 95 / 100`), and on a new pool the effective TWAP window can be very short (`period = min(30 min, longestPeriod)`). When spot price is above the TWAP (or the TWAP is manipulated upward briefly), `peek(amount)` systematically **underestimates** real ETH cost. `_contributed` therefore grows slower than the user’s true spend.
- **Impact:** A whitelisted buyer can repeatedly buy from the Uniswap V3 pool and exceed the intended per-address ETH cap (`_maxAddressCap`, default 3 ETH). The cap accounting is wrong, so the economic limit is bypassed.

**Vulnerable path:**
```solidity
uint256 estimatedETHAmount = IOracle(_oracle).peek(amount);
if (_contributed[to] + estimatedETHAmount > _maxAddressCap) revert;
_contributed[to] += estimatedETHAmount;
```
Real ETH spent in the swap can be materially higher than `estimatedETHAmount`.

---

## Manipulable TWAP on newly created pools

- **Location:** `UniswapV3Oracle.sol` : `peek` (via `OracleLibrary.getOldestObservationSecondsAgo` / `consult`)
- **Mechanism:** If the pool has little observation history, `longestPeriod` can be seconds (or zero-ish effective window). `consult` then uses that tiny window, so a single swap or short manipulation can move the “TWAP” almost arbitrarily. That manipulated value feeds directly into `Whitelist.checkWhitelist` cap accounting.
- **Impact:** An attacker can inflate or deflate `peek()` around their buys to under-credit `_contributed` (cap bypass above) or over-credit other users (griefing). This is especially practical right after pool creation / launch.

---

## Whitelist and lock only enforced on pool→user transfers (buy path)

- **Location:** `Whitelist.sol` : `checkWhitelist`
- **Mechanism:** All restrictions (`_locked`, blacklist, whitelist index, contribution cap) sit inside `if (from == _pool && to != owner())`. Every other transfer path is a no-op: user→pool (sell), user→user, mint/burn-adjacent flows, etc. `VultisigWhitelisted._beforeTokenTransfer` always calls `checkWhitelist`, but for non-buy transfers the function does nothing.
- **Impact:** During the “locked” launch phase:
  - Non-whitelisted addresses can receive VULT from a whitelisted buyer and **sell into the pool** (`from != _pool`, unrestricted).
  - Tokens can circulate freely on secondary transfers while pool buys remain gated.
  - Blacklisted addresses can still receive and move tokens if they are not the `to` on a pool buy.

This breaks the stated intent that `_beforeTokenTransfer` enforces whitelist eligibility broadly.

---

## Unset pool address disables all buy-side protections

- **Location:** `Whitelist.sol` : `checkWhitelist` (and owner setters `setPool`)
- **Mechanism:** Restrictions trigger only when `from == _pool`. `_pool` defaults to `address(0)` and is owner-set. If the owner wires oracle/vultisig but forgets `setPool`, or sets the wrong pool, buys from the real Uniswap pool never match `from == _pool`.
- **Impact:** While `_whitelistContract` is active, anyone can buy from the actual V3 pool with no lock, whitelist, blacklist, or cap checks. This is a deployment/configuration footgun with full bypass impact.

---

## `totalRaised` not decremented on user refund (broken sale accounting)

- **Location:** `ILOPool.sol` : `claimRefund`
- **Mechanism:** `claimRefund` burns the NFT, deletes position data, and returns `raiseAmount` in `RAISE_TOKEN`, but never reduces `totalRaised`. `launch()` later uses `totalRaised` (not token balance) to size liquidity: `amount0 = totalRaised` / `amount1 = totalRaised`, and checks `totalRaised >= softCap`.
- **Impact:**
  1. **Bricked launch:** After refund deadline, investors refund. `totalRaised` still reflects old deposits, but contract `RAISE_TOKEN` balance is lower. `launch()` tries to deploy more raise liquidity than exists → `pay()` / `transfer` fails → launch cannot succeed.
  2. **Hard-cap griefing:** Refunded capacity is not freed; `buy()` still sees reduced `hardCap - totalRaised`, so legitimate buyers may be blocked even though ETH was returned.
  3. **Misleading soft-cap signal:** `totalRaised >= softCap` can be true while most funds were refunded.

**Vulnerable path:** refund succeeds → `totalRaised` unchanged → `launch()` uses inflated `totalRaised`.

---

## Permissionless `initProject` — first caller becomes project admin

- **Location:** `ILOManager.sol` : `initProject`
- **Mechanism:** `initProject` has no access control. The first caller for a given Uniswap V3 pool becomes `_project.admin` and permanently occupies `_cachedProject[uniV3PoolAddress]` (`require(_project.uniV3PoolAddress == address(0), "RE")` blocks later legitimate registrants).
- **Impact:** An attacker can front-run a legitimate launch for a `(saleToken, raiseToken, fee)` pair, become admin, create malicious `ILOPool` clones, control whitelist (`setOpenToAll`, `batchWhitelist`), and phish deposits. Victims interacting with the attacker’s pool addresses lose raise funds or receive bad vesting terms.

---

## Pool price / project hijacking on existing uninitialized pools

- **Location:** `ILOManager.sol` : `_initUniV3PoolIfNecessary` / `initProject`
- **Mechanism:** If the Uniswap pool already exists but is uninitialized (`sqrtPriceX96 == 0`), the first `initProject` caller initializes it at **their** `initialPoolPriceX96` and becomes admin. If it is already initialized at a different price, later honest `initProject` calls revert `"UV3P"`.
- **Impact:** Attacker can initialize a victim token pair at an extreme price and capture project admin, or force the victim’s launch to bind to an attacker-chosen initial price/admin.

---

## `launch()` is permissionless and trusts stale `totalRaised`

- **Location:** `ILOManager.sol` : `launch` → `ILOPool.sol` : `launch`
- **Mechanism:** Anyone may call `ILOManager.launch` after `launchTime` if pool price matches. Combined with the refund accounting bug, launch can be attempted when economics are broken; even without refunds, a griefer can trigger launch at the first eligible block.
- **Impact:** Not always directly stealable, but enables griefing (forcing launch attempt / timing) and couples with the `totalRaised` bug to permanent project failure states.

---

## Owner exemption from all pool-buy restrictions

- **Location:** `Whitelist.sol` : `checkWhitelist`
- **Mechanism:** The guard is `if (from == _pool && to != owner())`. Transfers from the pool to `owner()` skip lock, whitelist index, blacklist, and `_maxAddressCap` / `_contributed` updates entirely.
- **Impact:** Compromised or malicious owner can accumulate unlimited VULT from the pool during the restricted launch period while other users are capped. If “owner” is a multisig this may be acceptable; if not, it is a privileged bypass of the sale rules.

---

## `approveAndCall` grants allowance before arbitrary external call (reentrancy / approval hijack)

- **Location:** `Vultisig.sol` : `approveAndCall`
- **Mechanism:** The contract sets `_approve(msg.sender, spender, amount)` and then synchronously calls `IApproveAndCallReceiver(spender).receiveApproval(...)`. A malicious `spender` can reenter token/DeFi logic while allowance is live. If `receiveApproval` does not atomically consume the full allowance, leftover approval remains usable.
- **Impact:** Users tricked into `approveAndCall` on a malicious contract can have tokens pulled via `transferFrom` beyond the intended atomic swap flow, or suffer reentrancy interactions with protocols that key off approvals/balances mid-tx. This is a classic approve-then-call hazard.

---

## `checkWhitelist` reverts if oracle unset (buy DoS)

- **Location:** `Whitelist.sol` : `checkWhitelist`
- **Mechanism:** On pool buys, the function unconditionally calls `IOracle(_oracle).peek(amount)`. If `_oracle` is `address(0)` or misconfigured, all pool buys revert.
- **Impact:** Not attacker profit, but a deployment mistake fully denies buying from the pool while the whitelist hook remains enabled — effective sale freeze.

---

## Summary table

| Severity | Finding |
|----------|---------|
| High | ETH cap bypass via underestimated `peek()` |
| High | TWAP manipulation on young pools |
| High | `totalRaised` not updated on refund → bricked launch / broken caps |
| High | Permissionless `initProject` admin takeover |
| Medium | Whitelist/lock only on pool buys; sells & transfers bypass |
| Medium | Unset/wrong `_pool` disables protections |
| Medium | Pool initialization / price front-running |
| Medium | `approveAndCall` approve-then-call risk |
| Low/Medium | Owner unlimited pool-buy bypass |
| Low | Unset oracle DoS |

---

**Note:** Several issues (oracle cap bypass, refund/`totalRaised`, permissionless `initProject`) interact in a full deployment: an attacker can squat the ILO project, launch the pool, manipulate a young TWAP, and buy VULT through the pool while evading per-address ETH limits.

I did not report pure centralization (owner can change oracle, pool, caps, whitelist contract) unless it created a concrete unintended code path above. If you want, I can map these findings to a specific attack timeline for the Vultisig + ILO deployment order.

