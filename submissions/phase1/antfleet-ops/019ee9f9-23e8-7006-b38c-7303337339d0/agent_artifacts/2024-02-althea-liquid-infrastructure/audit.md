# Audit: 2024-02-althea-liquid-infrastructure

# Security Audit: Liquid Infrastructure Contracts

Findings below are limited to **genuine logic/accounting vulnerabilities** in the production contracts (`LiquidInfrastructureERC20`, `LiquidInfrastructureNFT`, `OwnableApprovableERC721`). Test contracts are noted only where they introduce unsafe patterns if deployed.

---

## Duplicate `holders` entries allow multiple reward claims

- **Location:** `LiquidInfrastructureERC20.sol` : `_beforeTokenTransfer`, `_afterTokenTransfer`, `distribute`
- **Mechanism:** The `holders` array is maintained manually. On receive, `_beforeTokenTransfer` pushes `to` whenever `balanceOf(to) == 0` **without checking whether `to` is already in `holders`**. On full exit, `_afterTokenTransfer` removes `from` via swap-and-pop in a loop **without `break` and without re-checking index `i` after a swap**, so when duplicate entries exist one removal pass can leave a **zero-balance ghost** at index `i` while `i` advances and skips the swapped-in element. A later transfer/mint back to that address pushes a second entry while the ghost remains. In `distribute`, each array slot is paid independently: `entitlement = erc20EntitlementPerUnit[j] * balanceOf(recipient)`, so the same address with one non-zero balance can be paid multiple times in one distribution round.
- **Impact:** An attacker can inflate their payout by engineering duplicate self-entries (e.g., ghost creation via botched removal from `[Alice, Bob, Alice]`, then Bob sending all tokens to Alice to produce `[Alice, Alice]`). They drain reward ERC20s disproportionately; later recipients may receive nothing when the contract balance is exhausted.

**Vulnerable path:**

```solidity
// _beforeTokenTransfer — no membership check
bool exists = (this.balanceOf(to) != 0);
if (!exists) {
    holders.push(to);  // pushes even if `to` is already in `holders` with 0 balance
}

// distribute — pays per array slot, not per unique address
uint256 entitlement = erc20EntitlementPerUnit[j] * this.balanceOf(recipient);
```

---

## Burns append `address(0)` to `holders`, enabling unbounded list growth (DoS)

- **Location:** `LiquidInfrastructureERC20.sol` : `_beforeTokenTransfer`
- **Mechanism:** On every burn, `from != address(0)` and `to == address(0)`. The allowlist check is skipped for `to == 0`, but the holder-tracking logic still runs: `balanceOf(address(0)) == 0`, so `exists` is false and **`holders.push(address(0))` executes on every burn**. `address(0)` is never a real holder and is never cleaned up by `_afterTokenTransfer` (which only removes `from`, the burner).
- **Impact:** Any holder who burns (via `burn`, `burnFrom`, `burnAndDistribute`, etc.) permanently grows `holders`. An attacker can repeatedly mint (when allowed), transfer, and burn to bloat the array until `distribute()` / `distributeToAllHolders()` exceeds the block gas limit, **freezing distributions and locking the contract in `LockedForDistribution` mid-round** if a large distribution was started, or preventing `_beforeMintOrBurn` from ever being satisfiable if the period elapses.

**Vulnerable path:**

```solidity
function _beforeTokenTransfer(address from, address to, uint256 amount) internal override {
    // ...
    bool exists = (this.balanceOf(to) != 0);
    if (!exists) {
        holders.push(to);  // `to == address(0)` on burns
    }
}
```

---

## Silent ERC20 transfer failures cause skipped payouts and permanent fund stranding

- **Location:** `LiquidInfrastructureERC20.sol` : `distribute`
- **Mechanism:** Payout uses bare `IERC20.transfer()` and only records/emits when it returns `true`. Non-standard tokens (e.g., USDT) return `false` instead of reverting; fee-on-transfer / rebasing tokens can also cause effective transfer failure or shortfall. The function does **not** revert, still advances `nextDistributionRecipient`, and eventually calls `_endDistribution()` as if the round completed successfully.
- **Impact:** Some holders receive no rewards while the distribution finalizes and unlocks. Undistributed tokens remain in the contract but are not accounted for; on the next round, `entitlement = balance / supply` recomputes over the new balance, so **leftover rewards from the failed round are redistributed pro-rata to all holders**, diluting correct accounting and causing systematic loss for holders who were skipped (especially those processed late if the contract runs out of balance after earlier successful transfers). An attacker with duplicate entries (finding 1) can front-load successful payouts and leave later holders with failed transfers.

**Vulnerable path:**

```solidity
if (toDistribute.transfer(recipient, entitlement)) {
    receipts[j] = entitlement;
}
// no else/revert; loop continues and distribution can finish
```

---

## `releaseManagedNFT` never validates NFT removal (`require(true)`)

- **Location:** `LiquidInfrastructureERC20.sol` : `releaseManagedNFT`
- **Mechanism:** After attempting to remove `nftContract` from `ManagedNFTs`, the code uses `require(true, "unable to find released NFT in ManagedNFTs")`, which **always passes** even when the NFT was not in the array. The NFT is still transferred out via `nft.transferFrom(address(this), to, nft.AccountId())`.
- **Impact:** Owner (or compromised owner key) can release an NFT while it remains in `ManagedNFTs`. Subsequent `withdrawFromManagedNFTs()` calls hit that entry; `withdrawBalancesTo` reverts because the ERC20 contract is no longer `ownerOf(AccountId)` nor approved, **bricking the withdrawal sweep** until the stale address is removed by other means (there is no admin function to prune `ManagedNFTs`). Revenue from other NFTs cannot be collected in a single `withdrawFromAllManagedNFTs()` pass.

**Vulnerable path:**

```solidity
for (uint i = 0; i < ManagedNFTs.length; i++) {
    if (managed == nftContract) {
        ManagedNFTs[i] = ManagedNFTs[ManagedNFTs.length - 1];
        ManagedNFTs.pop();
        break;
    }
}
require(true, "unable to find released NFT in ManagedNFTs");  // dead/wrong check
```

---

## Integer-division dust is never distributed and accumulates indefinitely

- **Location:** `LiquidInfrastructureERC20.sol` : `_beginDistribution`
- **Mechanism:** Per-token entitlement is `balance / totalSupply()` (floor division). The remainder `balance % totalSupply()` is never assigned to any holder and no sweep function exists.
- **Impact:** A portion of every revenue collection is **permanently locked** in the ERC20 contract, reducing effective yield for all holders. While not directly stealable by an attacker without complementary bugs, it is a real accounting error that compounds every distribution period and can be nontrivial for tokens with small decimals or large `totalSupply`.

---

## Owner can rewrite `distributableERC20s` mid-distribution and desync payouts

- **Location:** `LiquidInfrastructureERC20.sol` : `setDistributableERC20s` (called during `LockedForDistribution == true`)
- **Mechanism:** `setDistributableERC20s` has no `!LockedForDistribution` guard. During an in-progress distribution, `erc20EntitlementPerUnit` was fixed at `_beginDistribution`, but `distribute()` iterates the **current** `distributableERC20s.length` and indexes into the stale `erc20EntitlementPerUnit` array.
- **Impact:** If the owner shortens the list, some entitled tokens are skipped for remaining recipients. If lengthened, new indices read zero entitlements (empty storage slots) and pay nothing for those assets while the round completes. **Misallocates or strands rewards** for holders processed after the change. Exploitable by a malicious or compromised owner key mid-round.

---

## Disapproved holders remain in `holders` and can grief distribution completion

- **Location:** `LiquidInfrastructureERC20.sol` : `disapproveHolder`, `distribute`, `_afterTokenTransfer`
- **Mechanism:** `disapproveHolder` only flips a mapping flag; it does not remove the account from `holders`. Disapproved accounts with a balance cannot receive new transfers in, but they are not forced to burn/transfer out. In `distribute`, they are skipped for payment (`if (isApprovedHolder(recipient))`) but still consume a distribution slot.
- **Impact:** A disapproved holder who retains tokens (or who was disapproved after acquiring tokens through a prior transfer chain) remains in the iteration queue. Combined with a large `holders` array (including `address(0)` ghosts from burns), this increases gas per distribution round and can contribute to **out-of-gas failure** of `distributeToAllHolders()` / `mintAndDistribute()` / `burnAndDistribute()`, blocking mint/burn gating that depends on completing a distribution after `MinDistributionPeriod`.

---

## `withdrawFromManagedNFTs` uses NFT threshold list, not `distributableERC20s` — revenue can be stranded in NFTs

- **Location:** `LiquidInfrastructureERC20.sol` : `withdrawFromManagedNFTs` ; `LiquidInfrastructureNFT.sol` : `getThresholds`
- **Mechanism:** Withdrawal pulls only `withdrawFrom.getThresholds()` tokens into the aggregator. `distributableERC20s` on the ERC20 contract is a separate, owner-editable list. If revenue tokens accrue in an NFT but are absent from that NFT’s threshold list (or thresholds are misconfigured), `withdrawBalancesTo` never moves them.
- **Impact:** Holders never receive those assets; funds sit in the NFT contract indefinitely unless the NFT owner/approved party manually changes thresholds and withdraws. Operational misconfiguration becomes a **loss-of-yield** condition for token holders (not attacker profit unless an approved NFT operator is malicious).

---

## Test contract: unrestricted `mint` in `TestERC20A`

- **Location:** `TestERC20A.sol` : `mint`
- **Mechanism:** `mint` is `public` with no access control.
- **Impact:** If deployed in production, anyone can inflate supply and break any economic assumptions. **Only relevant if test contracts are deployed**; not a production-path issue for the main protocol contracts themselves.

---

# Summary by severity

| Severity | Finding |
|----------|---------|
| **High** | Duplicate `holders` entries → multiple reward claims |
| **Medium** | Burns push `address(0)` → holder list DoS |
| **Medium** | Silent `transfer` failures → skipped payouts / unfair redistribution |
| **Medium** | `require(true)` in `releaseManagedNFT` → bricked withdrawal sweep |
| **Medium** | `setDistributableERC20s` during active distribution → desynced payouts |
| **Low** | Division remainder (dust) locked forever |
| **Low** | Disapproved holders retained in `holders` → gas griefing / distribution DoS |
| **Low** | Threshold vs. distributable token list mismatch → stranded NFT revenue |

---

# Recommended fix directions (guidance only)

1. Track holders with a `mapping(address => bool)` plus `address[]` only for enumeration, or check `holders` membership before `push`.
2. In `_afterTokenTransfer`, after swap-and-pop, **do not increment `i`** (or use `break` after single removal per event if duplicates should be impossible).
3. Never push `address(0)` in `_beforeTokenTransfer` (`if (to != address(0) && !exists)`).
4. Use `SafeERC20.safeTransfer` and revert on failure; consider `balanceBefore/after` for fee-on-transfer tokens.
5. Replace `require(true, ...)` with a `found` flag; require NFT ∈ `ManagedNFTs` before transfer.
6. Guard `setDistributableERC20s` with `!LockedForDistribution`.
7. Track and sweep `balance % supply` dust to a defined recipient or roll it into the next round explicitly.

I can expand any finding into a step-by-step PoC trace or suggested patch if you want to move to implementation mode.

