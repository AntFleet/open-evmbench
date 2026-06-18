# Audit: 2024-05-olas

## Consensus findings

## Arbitrary third party can force / grief a VotingEscrow lock on any address via `createLockFor`
*(consensus)*
- Location: `VotingEscrow-flatten.sol` : `createLockFor(address,uint256,uint256)` / `_createLockFor` (related path: `depositFor`)
- Mechanism: `createLockFor(account, amount, unlockTime)` lets any caller open the *first* lock for an arbitrary nonzero `account`, funding it from `msg.sender`'s tokens but writing `mapLockedBalances[account]`. The only precondition is that the account has no existing lock (`mapLockedBalances[account].amount == 0`). An attacker front-runs the victim's own `createLock` by calling `createLockFor(victim, 1, minWeek)` — seeding 1 wei with an attacker-chosen (short) `end`. Once `amount > 0` is set, the victim's `createLock` reverts (`LockedValueNotZero`) because `_createLockFor` rejects an existing locked balance; the victim can thereafter only add amount or extend the already-selected unlock time, not set their intended parameters.
- Impact: For a dust cost, an attacker can grief any address that has not yet created a lock, forcing it into an attacker-chosen lock duration (up to the 4-year max) and preventing the victim from creating a shorter or otherwise intended VotingEscrow lock until the dust lock expires and is withdrawn. Reviewer A notes the victim can still reach a usable state via `increaseUnlockTime` / `increaseAmount` (and the attacker forfeits the seeded tokens), so severity is low; it remains a genuine permissionless state-interference vector. Suggested fix: restrict `createLockFor` to `msg.sender == account` or a whitelisted depositor.

## Additional findings (single-reviewer)

## Voting power can be acquired after a proposal's snapshot (`getPastVotes` missing block-bound guard)
*(Reviewer A only)*
- Location: `VotingEscrow-flatten.sol` : `getPastVotes(address,uint256)` and helper `_findPointByBlock` (compare against `balanceOfAt` / `totalSupplyAt`)
- Mechanism: `_findPointByBlock(blockNumber, account)` returns the user point with the largest `blockNumber <= requested`, **but when every user point is after the requested block it falls through and returns `mapUserPoints[account][0]`** (the binary search leaves `minPointNumber == 0`). `balanceOfAt` / `totalSupplyAt` defensively re-check `if (uPoint.blockNumber < (blockNumber + 1)) return 0`, but `getPastVotes` does not — it directly extrapolates `uPoint.bias -= uPoint.slope * int128(int64(uint64(blockTime)) - int64(uPoint.ts))`. For the first lock point, `bias0 = slope*(end - ts0)`; when `blockTime < ts0` the subtraction *adds* `slope*(ts0 - blockTime)`, yielding `balance = slope*(end - blockTime)` — voting weight the lock would have had at a time before it existed (larger than at creation).
- Impact: Breaks the snapshot mechanism `GovernorOLA`/`GovernorVotes` relies on. `_castVote` reads weight via `token.getPastVotes(account, proposal.voteStart.getDeadline())`. A user can wait until a proposal is `Active` (`block.number > snapshot`), create a brand-new lock, and have `getPastVotes(account, snapshot)` return inflated weight because their only point has `blockNumber > snapshot` — voting (or meeting `proposalThreshold` in `propose`, which uses `getPastVotes(proposer, block.number-1)`) with stake acquired *after* the snapshot. Fix: add the `uPoint.blockNumber <= blockNumber` guard used in `balanceOfAt`.

## `buOLA._releasableAmount` multiplies in `uint96` inside `unchecked` (silent overflow of vesting math)
*(Reviewer A only)*
- Location: `buOLA-flatten.sol` : `_releasableAmount(LockedBalance)` (the `else` branch)
- Mechanism: In `unchecked { amount = uint256(lockedBalance.amountLocked * releasedSteps / numSteps); amount -= uint256(lockedBalance.amountReleased); }`, `amountLocked` is `uint96` and `releasedSteps` is `uint32`; by Solidity type promotion the product `amountLocked * releasedSteps` is computed in **`uint96`** and only cast to `uint256` after the multiplication. Because the block is `unchecked`, if the product exceeds `2^96-1` it wraps silently (`releasedSteps` can be up to 9 here). The wrapped, too-small product can then make `amount -= amountReleased` underflow to a huge value.
- Impact: For a single lock whose `amountLocked` approaches `~2^96/10 ≈ 8.7e27`, the released amount is computed incorrectly (and can underflow), corrupting withdrawal accounting. Bounded by OLAS supply (≈1e27 for the first decade, +2%/yr), so **not reachable today** — a latent correctness bug reachable only far in the future / for an implausibly large single locker. Safe fix: compute the product in `uint256` (`uint256(amountLocked) * releasedSteps / numSteps`) rather than relying on `unchecked`.

## Arbitrary third party can force a buOLA lock on any address
*(Reviewer B only)*
- Location: `buOLA-flatten.sol` : `createLockFor`
- Mechanism: `createLockFor(account, amount, numSteps)` is externally callable by anyone and initializes `mapLockedBalances[account]` as long as the account currently has no lock. Because subsequent lock creation requires `lockedBalance.amountLocked == 0`, the real account cannot create its intended buOLA lock after an attacker initializes a dust lock for it.
- Impact: An attacker can lock a minimal amount for a victim with `numSteps` up to `MAX_NUM_STEPS`, blocking the victim from creating its own lock schedule for up to 10 years — a low-cost denial of service against accounts that have not yet created a buOLA lock.

## Guard allows scheduled Arbitrum bridge calls to redirect ETH refunds
*(Reviewer B only)*
- Location: `GuardCM-flatten.sol` : `_verifySchedule`; `ProcessBridgedDataArbitrum-flatten.sol` : `processBridgeData`
- Mechanism: The guard verifies only the scheduled target and payload selector. For Arbitrum bridge calls, `processBridgeData` decodes the retryable ticket and checks only `targetAddress` and `targetPayload`; it does not validate `excessFeeRefundAddress`, `callValueRefundAddress`, gas parameters, or the ETH `value` scheduled through the timelock. `_verifySchedule` also discards the timelock `values` array entirely.
- Impact: A community-multisig transaction that passes the allowlist can schedule an authorized Arbitrum retryable ticket while setting refund recipients to attacker-controlled addresses and overfunding the call from the timelock. If the timelock holds ETH and the scheduled operation executes, the attacker can redirect retryable-ticket excess-fee / callvalue refunds on L2 while still using an allowed target and selector. (Note: Reviewer A reviewed `GuardCM` and `ProcessBridgedDataArbitrum` and judged them safe, focusing on guard self-removal protection, delegatecall storage-layout alignment, and the byte-parser bounds — not the refund-address / `value` validation gap B raises.)

