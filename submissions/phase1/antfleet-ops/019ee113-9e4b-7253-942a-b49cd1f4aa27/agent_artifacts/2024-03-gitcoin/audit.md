# Audit: 2024-03-gitcoin

Looking at this codebase, I need to analyze the IdentityStaking contract carefully, focusing on the staking, slashing, and release mechanics.

Let me trace through several scenarios to identify accounting bugs:

**Tracing the `release` function for accounting consistency:**

In every other code path that affects stake size, `userTotalStaked[staker]` is updated:
- `selfStake` / `communityStake`: `userTotalStaked += amount`
- `withdrawSelfStake` / `withdrawCommunityStake`: `userTotalStaked -= amount`
- `slash` (self or community): `userTotalStaked -= slashedAmount`

But in `release`, the function restores the slashed stake amount by incrementing `sStake.amount` (or `comStake.amount`) without correspondingly incrementing `userTotalStaked[staker]`.

**Concrete exploit scenario:**
- User A stakes 1000. `userTotalStaked[A] = 1000`, `sStake.amount = 1000`.
- Slash A 10%: `sStake.amount = 900`, `userTotalStaked[A] = 900`, `slashedAmount = 100`.
- Release A for 50: `sStake.amount = 950`, `slashedAmount = 50`, but `userTotalStaked[A]` remains 900 (BUG).
- Attempt to slash A with 100% (intending to slash 950): `slashedAmount = 950`. The line `userTotalStaked[staker] -= slashedAmount` computes `900 - 950`, which underflows and **reverts the entire transaction**.

The slash is reverted, leaving `sStake.amount = 950` untouched. The user retains the full 950 that should have been slashed. Any further slash attempts will also revert (since `userTotalStaked` stays at 900 and any subsequent subtraction will still underflow until `sStake.amount` itself drops below 900 via repeated small slashes — and even then, the inconsistency persists).

This contradicts the documented invariant that "all staked amounts are liable to be slashed."

**Tracing the move logic in `slash` (verifying it's actually correct):**

I want to confirm the comment "If this is a slash from the previous round (not yet burned)" is accurate. The condition is `slashedInRound == currentSlashRound - 1`. Since `lockAndBurn` increments `currentSlashRound` AFTER reading `roundToBurn = currentSlashRound - 1`, when `currentSlashRound = N+1`, round N has NOT yet been burned (only round N-1 was burned). The move correctly shifts the slash accounting from a not-yet-burned round to the new round, so the tokens will be burned in the correct round with no double-burn. This logic is correct.

**Reentrancy analysis:**

In `withdrawSelfStake` and `withdrawCommunityStake`, state is decremented before `token.transfer`. With a callback token, an attacker could re-enter `withdrawSelfStake`, but the second call would see the reduced `sStake.amount` and would only withdraw what's available — no over-withdrawal is possible (only `amount ≤ sStake.amount` is permitted).

**Other observations:**

- `withdrawSelfStake` lacks `amount == 0` check (minor inconsistency with `withdrawCommunityStake`, not exploitable).
- `release` emits no event (observability issue, not a vulnerability).
- The `Slash` event doesn't include the stakee for community-stake slashes (observability issue).
- `lockAndBurn` will revert (DoS) if the token transfer fails — this is a configuration concern if `burnAddress` is misconfigured.

---

## Findings

### `userTotalStaked` not updated in `release` (medium-high severity)

- **Location:** `IdentityStaking.sol` : `release`
- **Mechanism:** The `release` function restores a slashed stake by incrementing `selfStakes[staker].amount` (or `communityStakes[staker][stakee].amount`) and decrementing the corresponding `slashedAmount` and `totalSlashed[slashRound]`. However, it never increments `userTotalStaked[staker]`, so after every release the `userTotalStaked` value becomes stale and is lower than the sum of active stakes by exactly the released amount. This diverges from how every other stake-mutating function maintains the invariant.
- **Impact:**
  1. **Slashing evasion / DoS of slasher:** Subsequent `slash` calls compute a `slashedAmount` based on the per-stake `sStake.amount`, then attempt `userTotalStaked[staker] -= slashedAmount`. Because `userTotalStaked` is now lower than `sStake.amount` (by the released amount), this subtraction underflows for any slash whose `slashedAmount` exceeds the (incorrect) `userTotalStaked`. The transaction reverts, the slash is not applied, and the staker keeps funds that should have been slashed. The slasher is forced to perform many small slashes and can never fully slash the user, contradicting the documented "all staked amounts are liable to be slashed" guarantee.
  2. **Incorrect accounting for off-chain consumers:** Any integrator reading `userTotalStaked` (governance, voting, gating, reward distribution, etc.) receives a value lower than the actual sum of the user's active stakes.

### Suggested fix

Add `userTotalStaked[staker] += amountToRelease;` at the end of `release` (in both the self-stake and community-stake branches) to keep `userTotalStaked` consistent with `sStake.amount` / `comStake.amount`, matching the pattern used in `selfStake` / `communityStake`.
