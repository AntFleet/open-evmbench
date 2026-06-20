# Audit: 2024-03-gitcoin

I audited the production contract (`IdentityStaking.sol`); the files under `test_mocks/` are explicitly test-only and out of scope. I found one genuine, high-impact vulnerability.

## `release()` restores `amount` but never restores `userTotalStaked`, locking funds and corrupting the staked-total accounting
- Location: `id-staking-v2/contracts/IdentityStaking.sol` : `release` (and its interaction with `slash` / `withdrawSelfStake` / `withdrawCommunityStake`)
- Mechanism: When a stake is slashed, **both** the per-stake `amount` and the user's aggregate `userTotalStaked[staker]` are decremented:
  ```solidity
  sStake.amount -= slashedAmount;
  userTotalStaked[staker] -= slashedAmount;
  ```
  When a slash is later reversed via `release()`, only the per-stake `amount` is credited back; `userTotalStaked` is **never** re-incremented:
  ```solidity
  selfStakes[staker].slashedAmount -= amountToRelease;
  selfStakes[staker].amount += amountToRelease;   // amount restored
  // userTotalStaked[staker] NOT restored
  ```
  (The community-stake branch has the identical omission.) This leaves `userTotalStaked` permanently understated by `amountToRelease`, while `selfStakes[staker].amount` reflects the full restored balance. The two values are supposed to be kept in lock-step everywhere else in the contract.
- Impact: Two concrete harms:
  1. **Permanent fund lock-up.** Consider a staker with a single self-stake of 100, slashed 100% then fully released: `selfStakes.amount == 100` but `userTotalStaked == 0`. When the staker calls `withdrawSelfStake(100)`, the `amount > sStake.amount` check passes, but the subsequent `userTotalStaked[msg.sender] -= 100` underflows `0 - 100` and reverts. The released stake can never be withdrawn — the user's funds are stranded in the contract.
  2. **Accounting corruption for users with multiple stakes.** If the staker holds other stakes large enough to cover the withdrawal, the underflow doesn't trigger, but the withdrawal silently debits `userTotalStaked` against those *unrelated* stakes. `userTotalStaked` — the value exposed through `IIdentityStaking.userTotalStaked` and consumed by the Passport identity-scoring system — becomes wrong for that user, and a later full withdrawal of the remaining stakes will itself underflow and revert, again locking funds.

  Because a release is a routine remediation of a slash (an honest staker who successfully appeals), any released staker is exposed to this; it is reachable through normal, intended operation rather than requiring privileged misuse.

I examined the other plausible problem areas — the cross-round `totalSlashed` move logic in `slash()`, the `lockAndBurn` round/burn sequencing, the stale-slash `slashedAmount = 0` reset, lock-time overflow in `selfStake`/`communityStake`, and reentrancy on the token transfers — and found them sound (state updates precede transfers, and the round bookkeeping conserves slashed totals without double-burning or underflowing). The `userTotalStaked` asymmetry above is the one real vulnerability.

