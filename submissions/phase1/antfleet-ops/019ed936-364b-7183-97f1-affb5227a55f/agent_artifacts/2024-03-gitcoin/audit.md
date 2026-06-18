# Audit: 2024-03-gitcoin

Both reports cover the same codebase. After comparing root causes and code paths, two findings appear in both (the `release()`/`userTotalStaked` desync and the `slash()` `uint88` overflow), and one finding (the `initialize()` admin validation) appears only in Report A. Here is the merged report.

---

# Merged Security Audit Report — `IdentityStaking.sol`

## Consensus findings

## Released stake is never restored to `userTotalStaked`, locking released funds
*(consensus)*
- Location: `id-staking-v2/contracts/IdentityStaking.sol` : `release()` (around lines 500–535; the two branches doing `selfStakes[staker].amount += amountToRelease;` / `communityStakes[staker][stakee].amount += amountToRelease;`, plus the trailing `totalSlashed[slashRound] -= amountToRelease;`)
- Mechanism: When a stake is slashed, `slash()` decrements both the per‑stake `amount` and the aggregate `userTotalStaked[staker]` by `slashedAmount`. The inverse operation, `release()`, restores the per‑stake `amount` (`selfStakes[staker].amount += amountToRelease` / community equivalent) and reduces `selfStakes[staker].slashedAmount` and `totalSlashed[slashRound]`, but it never executes a matching `userTotalStaked[staker] += amountToRelease`. This desynchronizes the aggregate user balance from the restored per‑stake balance: after a slash‑then‑release cycle the per‑stake `amount` is fully restored while `userTotalStaked[staker]` stays permanently understated by the released amount. Precondition: the stake was slashed and then released by `RELEASER_ROLE`.
- Impact: The user can no longer withdraw the funds correctly returned to them. In `withdrawSelfStake` / `withdrawCommunityStake`, the amount check is against the per‑stake `amount` (restored), but the function then does `userTotalStaked[msg.sender] -= amount`; because `userTotalStaked` was not restored, withdrawing the full restored stake underflows and reverts (Solidity 0.8 checked arithmetic). Concretely: stake 100 → slash 50% → `amount=50, userTotalStaked=50` → release 50 → `amount=100, userTotalStaked=50`; an attempt to withdraw the 100 reverts, and at most 50 is ever withdrawable. The honestly‑restored funds are bricked in the contract, and every external consumer reading the public `userTotalStaked` gets a permanently too‑low value. A subsequent slash on the same staker can also underflow and revert, so the released stake becomes partially unwithdrawable and partially unslashable, and batch slashes including that staker can be DoSed.

## Large-stake slashing overflows `uint88` before division (DoS)
*(consensus)*
- Location: `id-staking-v2/contracts/IdentityStaking.sol` : `slash()` (self‑stake and community‑stake loops, around lines 445–495) — `uint88 slashedAmount = (percent * selfStakes[staker].amount) / 100;` and `uint88 slashedAmount = (percent * communityStakes[staker][stakee].amount) / 100;`
- Mechanism: Both `percent` and `.amount` are `uint88`, so the product `percent * amount` is evaluated in `uint88` *before* the `/ 100`. With checked arithmetic this overflows and reverts whenever `percent * amount > 2^88 − 1`, even though the final divided result (≤ `amount`) would always fit in `uint88`. `uint88` max is ≈ 3.09e26 (≈309M tokens at 18 decimals), so the revert threshold is roughly `amount > type(uint88).max / percent`.
- Impact: The slashing mechanism — the contract's core fraud‑response tool — becomes unusable against exactly the large stakers it most needs to penalize. For a 100% slash, any stake above ≈3.09M tokens (`type(uint88).max / 100`) cannot be slashed through this path; for a single holder of the full 100M supply, even a ~4% slash reverts. A single oversized entry in the `selfStakers`/`communityStakers` batch reverts the entire batch. Precondition: the attacker controls or receives a large enough stake balance. Fix: widen the intermediate math, e.g. `uint88 slashedAmount = uint88((uint256(percent) * amount) / 100);` (result always fits `uint88` since it's ≤ `amount`).

## Additional findings (single-reviewer)

## `initialize()` does not validate `initialAdmin`
*(Reviewer A only)*
- Location: `id-staking-v2/contracts/IdentityStaking.sol` : `initialize()` (the `_grantRole(DEFAULT_ADMIN_ROLE, initialAdmin)` / `_grantRole(PAUSER_ROLE, initialAdmin)` block)
- Mechanism: `tokenAddress` is checked against `address(0)`, but `initialAdmin` is not. If it is set to the zero address, `DEFAULT_ADMIN_ROLE` and `PAUSER_ROLE` are granted to `address(0)`, leaving the proxy with no controllable admin. Additionally, under the standard UUPS pattern `initialize()` is a separate public call guarded only by the `initializer` modifier, so if deployment and initialization are not performed atomically, the initializer can be front‑run.
- Impact: A zero `initialAdmin` permanently removes upgrade and pause control with no recovery path (only the admin can grant roles). A front‑run initializer hands an attacker `DEFAULT_ADMIN_ROLE`, i.e. full upgrade authority over user funds. These are configuration/deployment‑time issues rather than runtime‑exploitable, hence lower severity; mitigate with a zero‑address guard and an atomic deploy‑and‑init.

---

*Note: Report A also documented several paths it checked and deemed safe (checks‑effects‑interactions ordering in stake/withdraw, slash round‑migration consistency, `currentSlashRound - 1` underflow safety, slash rounding favoring the staker, and `uint64(block.timestamp)` downcasts). These are not findings and are recorded only as scope context.*

