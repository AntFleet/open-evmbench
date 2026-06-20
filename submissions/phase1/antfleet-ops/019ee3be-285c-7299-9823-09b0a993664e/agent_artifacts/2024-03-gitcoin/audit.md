# Audit: 2024-03-gitcoin

**Missing state update for `userTotalStaked` on slash release**

- Location: `IdentityStaking.sol` : `release`
- Mechanism: The `release` function (both the `staker == stakee` and `else` branches) performs `slashedAmount -= amountToRelease` and `amount += amountToRelease` on the relevant `Stake` struct and subtracts from `totalSlashed[slashRound]`, but never executes the matching `userTotalStaked[staker] += amountToRelease` (the inverse of the subtraction performed in `slash`).
- Impact: `userTotalStaked` permanently under-reports a user's actual stake after any release. Any downstream contract or off-chain system that trusts `userTotalStaked` (or the `IIdentityStaking` view) will see incorrect totals, enabling incorrect reward calculations, eligibility checks, or governance weight.

**Reentrancy via ERC-20 callbacks after state mutation**

- Location: `IdentityStaking.sol` : `selfStake`, `communityStake`, `withdrawSelfStake`, `withdrawCommunityStake`, `lockAndBurn`
- Mechanism: All four functions that move tokens perform the external `transfer`/`transferFrom` call *after* updating `Stake` structs, `userTotalStaked`, `totalSlashed`, and emitting events (violating checks-effects-interactions). A malicious or callback-enabled token can therefore re-enter the contract while the accounting state already reflects the transfer.
- Impact: An attacker can cause double-counting of stake, bypass the `unlockTime` check on withdrawal, or drain funds if the re-entrant path reaches another token-moving function before the first call returns.

**Stale-round slash data can be silently overwritten without updating aggregates**

- Location: `IdentityStaking.sol` : `slash` (both self-staker and community-staker loops)
- Mechanism: When `sStake.slashedInRound != currentSlashRound && != currentSlashRound-1`, the code does `sStake.slashedAmount = 0` but never subtracts the old `slashedAmount` from `totalSlashed[oldRound]`. The subsequent `totalSlashed[currentSlashRound] += slashedAmount` therefore double-counts or leaves phantom slashed totals.
- Impact: `totalSlashed` becomes inconsistent with actual stake; a later `lockAndBurn` can burn an incorrect amount or a `release` from the wrong round can succeed/fail unexpectedly.

**`lockAndBurn` can be called with zero `burnRoundMinimumDuration` after initialization**

- Location: `IdentityStaking.sol` : `initialize`, `lockAndBurn`
- Mechanism: `initialize` hard-codes `burnRoundMinimumDuration = 90 days`, but nothing prevents a subsequent upgrade or admin action from setting it to 0 (the field is public and has no setter). With a zero duration the `MinimumBurnRoundDurationNotMet` check is always bypassed.
- Impact: An attacker (or compromised SLASHER) can rapidly advance `currentSlashRound`, immediately burning the previous round's slashed tokens and eliminating the intended 90-day appeal window.
