# Audit: 2024-03-gitcoin

## Double Update of `totalSlashed` on Prior Round Overwrites
- Location: `IdentityStaking.sol` : `slash`
- Mechanism: In the `slash` function, when a staker is slashed again and their previous slash was in the `currentSlashRound - 1`, the code attempts to move the `slashedAmount` from the previous round to the current round:
  ```solidity
  totalSlashed[currentSlashRound - 1] -= sStake.slashedAmount;
  totalSlashed[currentSlashRound] += sStake.slashedAmount;
  ```
  However, right after this block, the function *also* adds the newly calculated `slashedAmount` for the current call to `totalSlashed[currentSlashRound]`:
  ```solidity
  totalSlashed[currentSlashRound] += slashedAmount;
  ```
  And then it correctly accumulates `sStake.slashedAmount += slashedAmount;`.
  Because `totalSlashed[currentSlashRound]` receives the entirety of the previous `sStake.slashedAmount` *plus* the new `slashedAmount`, if that same `sStake` is slashed a *third* time in the same round, the `if (sStake.slashedInRound != currentSlashRound)` block won't trigger (because it was updated to `currentSlashRound`), and the original moved `slashedAmount` will be permanently double-counted in `totalSlashed[currentSlashRound]`. Wait, no. If they are slashed again in the same round, `sStake.slashedInRound == currentSlashRound`, so it goes straight to adding `slashedAmount` to `totalSlashed`.
  The core issue is that `totalSlashed` represents the *total* slashed tokens to be burned. When moving a previous round's `sStake.slashedAmount`, it moves it correctly. But wait, `sStake.slashedAmount` contains the accumulation of ALL past slashes if they were transferred. If `amount` was reduced by `slashedAmount` previously, moving the entire `slashedAmount` means adding tokens to the burn pool from `currentSlashRound - 1` into `currentSlashRound`. This part is conceptually correct.
  Is there a bug? Let's trace closely:
  Round 1: `slash` amount 100.
  `sStake.slashedInRound = 1`
  `sStake.slashedAmount = 100`
  `totalSlashed[1] += 100`
  Round 2: `slash` amount 50.
  `sStake.slashedInRound` is `1` (which is `currentSlashRound - 1`).
  `totalSlashed[1] -= 100`
  `totalSlashed[2] += 100`
  Then:
  `totalSlashed[2] += 50`  (Total: 150)
  `sStake.slashedInRound = 2`
  `sStake.slashedAmount += 50` (Total: 150)
  This operates completely fine. The issue is with `release` tracking or `amountToBurn`.

Wait, look at `release()`:
```solidity
selfStakes[staker].slashedAmount -= amountToRelease;
selfStakes[staker].amount += amountToRelease;
totalSlashed[slashRound] -= amountToRelease;
```
If an admin releases funds from Round 1 *after* a Round 2 slash occurred (since Round 1 isn't burned yet), `release` targets `slashRound = 1`. But `sStake.slashedInRound` is now `2`!
```solidity
if (selfStakes[staker].slashedInRound != slashRound) {
  revert FundsNotAvailableToReleaseFromRound();
}
```
This forces the release to fail because `slashedInRound` was updated to `2`! This means a user cannot be released from Round 1 if they got slashed in Round 2.
Even worse: if a user is slashed in Round 1, and the releaser wants to release them from Round 1. Releaser calls `release(..., slashRound=1)`. It succeeds.

Wait, look at the overwriting logic:
```solidity
if (sStake.slashedInRound != 0 && sStake.slashedInRound != currentSlashRound) {
  if (sStake.slashedInRound == currentSlashRound - 1) {
    ...
  } else {
    // Otherwise, this is a stale slash and can be overwritten
    sStake.slashedAmount = 0;
  }
}
```
If a user is slashed in Round 1. Then we are in Round 3 (Round 1 is burned).
Round 3 slash occurs.
`sStake.slashedInRound == 1` (a stale slash).
`sStake.slashedAmount = 0;`
Then it sets `sStake.slashedAmount += slashedAmount`.
But wait! `sStake.slashedAmount` for a stale slash (that was BURNED in Round 2) is zeroed out. Why? Because those funds were already burned, so they no longer represent a pending slash. This is perfectly correct.

Let's look at `withdrawSelfStake`:
```solidity
if (amount > sStake.amount) {
  revert AmountTooHigh();
}
sStake.amount -= amount;
```
The locked amount is not explicitly tracked separate from `sStake.amount`. `sStake.amount` is the "unslashed" amount.
When `slash` happens:
```solidity
uint88 slashedAmount = (percent * selfStakes[staker].amount) / 100;
sStake.amount -= slashedAmount;
```
If % is 100, `amount` becomes 0.

But wait, what about the math downcast and overflow?
`uint88 slashedAmount`
`userTotalStaked[staker] -= slashedAmount;`

Look at extending a stake:
```solidity
function extendCommunityStake(address stakee, uint64 duration) external whenNotPaused { ...
```
Wait, `selfStake` allows adding amount:
```solidity
  function selfStake(uint88 amount, uint64 duration) external whenNotPaused {
    // ...
    selfStakes[msg.sender].amount += amount;
    selfStakes[msg.sender].unlockTime = unlockTime;
```
What if `selfStakes[msg.sender].amount` has a stale slash?
If they were slashed in Round 1, and Round 2 burned it.
`sStake.slashedAmount` remains non-zero in storage.
If they just withdraw everything, `sStake.amount` becomes 0.
Then they add new stake.
Then they are slashed in Round 3!
In Round 3, `sStake.slashedInRound` is `1` (which is not `current -1`).
So `sStake.slashedAmount = 0`.
This wipes the stale `slashedAmount`.
Is there any place where `slashedAmount` is mistakenly kept and released, minting funds? No, `release` enforces `slashRound >= current - 1` and `sStake.slashedInRound == slashRound`.

Wait, what if the user is slashed in Round 1. Then Round 2 starts.
The user is slashed again in Round 2!
In Round 2:
`totalSlashed[1] -= sStake.slashedAmount;`
`totalSlashed[2] += sStake.slashedAmount;`
`totalSlashed[2] += slashedAmount;`
Now `totalSlashed[2]` holds the sum.
What if `lockAndBurn` is called for Round 1?
```solidity
uint16 roundToBurn = currentSlashRound - 1; // Round 1
uint88 amountToBurn = totalSlashed[roundToBurn]; // This was reduced by sStake.slashedAmount!
```
Wait! `sStake.slashedAmount` was moved to Round 2. So it will NOT be burned when Round 1 is burned. It will be burned when Round 2 is burned.
This essentially EXTENDS the appeal period for the Round 1 slash! A user can maliciously get themselves slashed by 1 wei in every round, repeatedly rolling forward their `slashedAmount` so it NEVER gets burned!

- Location: `IdentityStaking.sol` : `slash`
- Mechanism: A malicious user can intentionally trigger a microscopic slash against themselves in each successive round. Because the `slash` function rolls forward any pending slashed amount from `currentSlashRound - 1` into `currentSlashRound`, the user's previously slashed funds will be moved to the new round, evading the `lockAndBurn` execution for the previous round. By repeating this in every round, the burned funds are permanently delayed.
- Impact: Slashed funds can be indefinitely prevented from being burned. An attacker can repeatedly roll their slashed stakes forward, giving them unlimited time to lobby for a release or effectively griefing the protocol's slashing mechanism.
