# Audit: 2024-02-althea-liquid-infrastructure
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## `holders` array poisoning on burn — `address(0)` push causes unbounded growth (distribution DoS)
*(consensus, 5 of 6 reports)*
- Location: `LiquidInfrastructureERC20.sol` : `_beforeTokenTransfer` (root-caused via `burn`/`burnFrom`/`_burn`)
- Mechanism: On any burn, `_burn` calls `_beforeTokenTransfer(from, address(0), amount)`. Membership is inferred as `bool exists = (this.balanceOf(to) != 0)`; `balanceOf(address(0))` is always `0`, so every burn unconditionally executes `holders.push(address(0))`. `_afterTokenTransfer` only removes `from`, never `address(0)`, and the mint-path cleanup loop uses swap-and-pop with no `break`, so it skips the swapped-in element and cannot drain duplicates. `burn(0)` is reachable by any address (no balance/approval needed) whenever the contract is not locked and not past the min-distribution period.
- Impact: An unauthenticated attacker can call `burn(0)` repeatedly (or any holder can burn 1 wei at a time) to grow `holders` without bound. `distributeToAllHolders()` (single-tx `distribute(holders.length)`) eventually exceeds the block gas limit and becomes un-callable; every paginated `distribute()` and every mint's cleanup loop pay ever-increasing gas over junk entries. Also permanently bloats storage and skews `holders.length`. No direct theft — `address(0)` fails `isApprovedHolder` and is skipped for payment.

## Duplicate `holders` entries via zero-value transfers → multiplied distribution payouts (reward theft / lock)
*(consensus, 4 of 6 reports)*
- Location: `LiquidInfrastructureERC20.sol` : `_beforeTokenTransfer` / `_afterTokenTransfer` / `distribute`
- Mechanism: Membership is approximated by `balanceOf(to) != 0` with no dedup guard, and OpenZeppelin ERC20 permits zero-value transfers. An attacker calls `transfer(approvedZeroBalanceHolder B, 0)` repeatedly while `B` has zero balance; each call passes the `isApprovedHolder(B)` check and `balanceOf(B)==0`, so `B` is pushed again and again. `_afterTokenTransfer` only ever removes `from`, never `to`, so the duplicates persist. The attacker then funds `B` and triggers `distribute`, which iterates every array slot and pays `erc20EntitlementPerUnit[j] * balanceOf(B)` once per duplicate entry.
- Impact: An approved holder (a normal investor) can inflate its `holders` multiplicity arbitrarily for the cost of zero-value transfers and collect N× its fair share of every distribution, draining the reward pool and stealing later holders' entitlements; duplicates are permanent so the theft repeats. Additionally, if duplicate over-payments exceed the reward-token balance, standard ERC20 transfers revert mid-distribution and the distribution can never finish, leaving `LockedForDistribution` stuck (freezing transfers/mints/burns) until extra rewards are donated. Some reports frame the same code path purely as a bloat/DoS hazard rather than theft.
- Reviewer disagreement: opus shot 1 explicitly defends this path — "I confirmed a real approved holder cannot be duplicated in `holders`" — denying the multiplied-payout theft.

## `setDistributableERC20s` is not locked during a distribution → entitlement/token index desync
*(consensus, 4 of 6 reports)*
- Location: `LiquidInfrastructureERC20.sol` : `setDistributableERC20s` vs. `_beginDistribution` / `distribute`
- Mechanism: `_beginDistribution` snapshots one `erc20EntitlementPerUnit[j]` per token, positionally aligned to `distributableERC20s` at that moment; `distribute` iterates `for j < distributableERC20s.length` and reads `erc20EntitlementPerUnit[j]`. `setDistributableERC20s` has no `require(!LockedForDistribution)` guard, so it can be called mid-distribution. A longer new list makes `erc20EntitlementPerUnit[j]` revert out-of-bounds on every remaining `distribute()` call; a shorter/reordered list pays holders an entitlement computed for a *different* token at index `j`.
- Impact: An owner reconfiguration (deliberate or accidental) during the multi-call distribution window either permanently wedges the contract in the locked state (DoS, freezing all transfers/mints/burns) or causes mismatched/over-large payouts (wrong amounts of the wrong tokens), potentially reverting on insufficient balance. The setter should reject calls while `LockedForDistribution` is true.

## Precision loss in entitlement math (divide-before-multiply) zeroes out and strands rewards
*(consensus, 3 of 6 reports)*
- Location: `LiquidInfrastructureERC20.sol` : `_beginDistribution` (`uint256 entitlement = balance / supply;`) and `distribute` (`entitlement = erc20EntitlementPerUnit[j] * this.balanceOf(recipient)`)
- Mechanism: Per-unit entitlement is computed as `rewardBalance / totalSupply`, floored, and only afterward multiplied by each holder's balance — the classic divide-then-multiply antipattern. The LIQ token is 18-decimal, so `totalSupply()` is ~`1e18` per whole share. Whenever the reward balance (in its own base units) is smaller than `supply` — e.g. a 6-decimal reward token (USDC) with `supply = 100e18`, where even `1000e6` gives `1000e6 / 100e18 == 0` — entitlement truncates to `0` and every holder is paid `0 * balance == 0`. Correct form is `rewardBalance * balanceOf(recipient) / totalSupply`.
- Impact: Under realistic decimal/supply combinations, all distributions silently pay nothing while rewards accumulate undistributed with no path to ever being paid (mint/burn become blocked once past the min-distribution period, and re-running `distribute` keeps producing zero). Even when nonzero, up to `supply - 1` base units per token are lost to truncation each round, and stranded leftovers leak into later holders' future distributions. Defeats the contract's core revenue-distribution purpose.
- Reviewer disagreement: opus shot 1 characterizes this rounding as harmless — "rounds down and only ever leaves dust in the contract — it cannot over-distribute" — i.e. not a vulnerability.

## `releaseManagedNFT` "found" check is a no-op (`require(true,...)`)
*(consensus, 3 of 6 reports)*
- Location: `LiquidInfrastructureERC20.sol` : `releaseManagedNFT`
- Mechanism: The function transfers the NFT out (`nft.transferFrom(address(this), to, nft.AccountId())`) first, then loops to swap-and-pop the matching `ManagedNFTs` entry, then executes `require(true, "unable to find released NFT in ManagedNFTs")` — a constant that can never revert. The intended post-condition (verify the NFT was actually present before releasing) is dead code, so any "not found" condition is silently swallowed and `ReleaseManagedNFT` is still emitted. Because `addManagedNFT` performs no duplicate check, the same NFT can be added twice; `releaseManagedNFT` removes only the first occurrence (`break`), leaving a stale entry the contract no longer owns.
- Impact: Bookkeeping desync between `ManagedNFTs` and actual ownership; the safety invariant the check was meant to enforce is absent. A resulting stale entry causes a later `withdrawFromManagedNFTs` to call `withdrawBalancesTo` on an NFT the contract no longer controls, reverting and DoS-ing the withdrawal pagination. Requires owner access; partial protection comes only from `nft.transferFrom` reverting when the contract is not the owner.

## Distribution permanently bricked by a reverting reward-token transfer
*(consensus, 2 of 6 reports)*
- Location: `LiquidInfrastructureERC20.sol` : `distribute` (inner `if (toDistribute.transfer(recipient, entitlement))` loop)
- Mechanism: `_beginDistribution` sets `LockedForDistribution = true`; `distribute` pays holders in a paginated loop, and the lock is cleared only in `_endDistribution` once `nextDistributionRecipient == holders.length`. If any single `transfer` to an approved holder *reverts* (rather than returning `false`) — e.g. a USDC/USDT-style token where that holder is blocklisted, or a paused token — the whole call reverts, the cursor never advances past that holder, and `LockedForDistribution` stays `true` forever. While locked, `_beforeTokenTransfer`'s `require(!LockedForDistribution)` blocks all transfers/mints/burns, and `withdrawFromManagedNFTs` is blocked too.
- Impact: A single problematic holder/token freezes the entire token and all revenue withdrawal indefinitely. Recoverable only by the owner calling `disapproveHolder(badHolder)` (which works while locked, as it makes no transfer) so `distribute` skips that recipient — but the contract is bricked until the owner identifies and disapproves the offender. Realistic trigger for blocklist-capable reward tokens.

## `TestERC20A` exposes an unrestricted public `mint`
*(consensus, 2 of 6 reports)*
- Location: `TestERC20A.sol` : `mint`
- Mechanism: `function mint(address to, uint256 amount) public { _mint(to, amount); }` has no access control — anyone can mint unlimited tokens.
- Impact: Informational; this is a test fixture (`TestERC20A/B/C`), not deployed production code. Flagged so it is never reused in production or as a real distributable reward token — if it were, any user could mint reward tokens to themselves at will.
- Reviewer disagreement: opus shot 3 excludes the `TestERC20*`/`TestERC721A` files entirely as "throwaway test mints [that] contain nothing exploitable."

## Minority findings

## `withdrawFromManagedNFTs` violates CEI and lacks a reentrancy guard
*(minority, 1 of 6 reports)* *(conflicting reviews: 1 of 6 reports defended this code path)*
- Location: `LiquidInfrastructureERC20.sol` : `withdrawFromManagedNFTs`
- Mechanism: Unlike `distribute`/`mint`/`releaseManagedNFT`, this function is not `nonReentrant`. It makes external calls inside the loop (`withdrawFrom.getThresholds()` and `withdrawFrom.withdrawBalancesTo(...)`, the latter performing ERC20 transfers into the contract) and only updates the `nextWithdrawal` cursor *after* the loop. If a managed NFT's threshold list includes a token with transfer hooks (ERC777-style), control can re-enter `withdrawFromManagedNFTs` (or `distribute`, which is not locked at this point) before `nextWithdrawal` is committed, replaying the same NFT indices.
- Impact: Reentrancy/CEI defect that can desync withdrawal accounting and interleave a distribution with an in-progress withdrawal. Practical fund loss is bounded (re-withdrawing an already-drained NFT moves a zero balance).
- Reviewer disagreement: opus shot 2 defends this path — the only external calls are to owner-added NFTs performing standard ERC20 transfers, and a reentry would re-read the same `nextWithdrawal` cursor and find zero balances, so it is "not independently exploitable absent an ERC777-style reward token (worth hardening, but not a confirmed vuln)."

## `distribute` silently ignores failed reward transfers (return value `false`)
*(minority, 1 of 6 reports)*
- Location: `LiquidInfrastructureERC20.sol` : `distribute` (`if (toDistribute.transfer(...)) { receipts[j] = entitlement; }`)
- Mechanism: When a reward token's `transfer` returns `false` (rather than reverting), the receipt is left at `0`, the loop continues, and the cursor advances past the holder without paying them — no revert, no retry. The emitted `Distribution` event then reflects `0` for that token even though entitlement existed.
- Impact: Holders can be silently under-paid for a round (funds stay in the contract and roll into the next round's entitlement), and on-chain `Distribution` events under-report actual entitlements, complicating accounting/monitoring. Genuine but not a fund-loss bug on its own.

---

*Distinct findings identified across the 6 input reports: 9. Findings emitted: 9 (7 consensus, 2 minority). No findings dropped.*

