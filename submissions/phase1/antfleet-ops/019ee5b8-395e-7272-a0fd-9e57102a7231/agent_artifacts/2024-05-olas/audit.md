# Audit: 2024-05-olas

## Post-snapshot locks receive voting power
- Location: `governance/audits/internal/analysis/contracts/VotingEscrow-flatten.sol` : `getPastVotes`
- Mechanism: `_findPointByBlock()` can return a user’s first checkpoint even when that checkpoint was created after the requested `blockNumber`. `getPastVotes()` then uses that future point without checking `uPoint.blockNumber <= blockNumber`, unlike `balanceOfAt()`. The bias calculation extrapolates backwards in time and gives the account voting power before the lock existed.
- Impact: An attacker can wait until a proposal snapshot has passed, create a new OLA lock, and still vote on that proposal with the newly acquired voting power, bypassing Governor snapshot protection.

## Active Safe guard permits unchecked timelock and direct calls
- Location: `governance/audits/internal10/analysis/contracts/GuardCM-flatten.sol` : `checkTransaction`
- Mechanism: While active, the guard only blocks delegatecalls, self-calls, and validates `schedule` / `scheduleBatch` calls sent to the timelock. Calls to the timelock with any other selector, such as `cancel(bytes32)`, are allowed without target-selector checks; calls to non-timelock targets are also allowed without `_verifyData()`.
- Impact: A compromised or colluding community multisig can bypass the intended allowlist. If it has `CANCELLER_ROLE`, which OpenZeppelin timelocks grant to proposers, it can cancel queued governance operations and block approved DAO proposals.

## Revoked buOLA locks corrupt released accounting
- Location: `governance/audits/internal/analysis/contracts/buOLA-flatten.sol` : `revoke`, `withdraw`
- Mechanism: `revoke()` writes `lockedBalance.amountReleased = uint96(amountRelease)`, but `_releasableAmount()` returns only the newly claimable delta, not the cumulative amount already released. After a partial withdrawal, this overwrites the cumulative released total. Later `withdraw()` computes `amountBurn = amountLocked - amountReleased`, burning too much OLA, and then also transfers the releasable amount. If revoke occurs before any vesting step, `amountReleased` is zero and `withdraw()` reverts before cleanup.
- Impact: Revoked users can become permanently unable to withdraw. If the contract holds enough pooled OLA from other users, the excessive burn can consume other users’ backing tokens.

## Anyone can force an initial lock for another account
- Location: `governance/audits/internal/analysis/contracts/VotingEscrow-flatten.sol` : `createLockFor`; `governance/audits/internal/analysis/contracts/buOLA-flatten.sol` : `createLockFor`
- Mechanism: Both `createLockFor` functions let any caller create the first lock for any nonzero `account`, funded from the caller but written into the victim’s lock slot. The only protection is that the victim must not already have a lock.
- Impact: An attacker can front-run or preempt a target with a dust lock and attacker-chosen duration. In `buOLA`, this can block the target from receiving an intended vesting lock for up to the maximum schedule; in `VotingEscrow`, it forces the victim into attacker-chosen initial lock parameters.

