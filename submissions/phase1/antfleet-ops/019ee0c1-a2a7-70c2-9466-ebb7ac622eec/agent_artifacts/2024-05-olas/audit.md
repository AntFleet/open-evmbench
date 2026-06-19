# Audit: 2024-05-olas

## Post-snapshot locks receive voting power

- Location: `governance/audits/internal/analysis/contracts/VotingEscrow-flatten.sol` : `getPastVotes`
- Mechanism: `_findPointByBlock()` returns the first user point even when that point was created after the requested `blockNumber`. `getPastVotes()` does not verify that `uPoint.blockNumber <= blockNumber` before using it, unlike `balanceOfAt()`. If an account has no prior checkpoints, it can create a lock after a proposal snapshot and `getPastVotes()` will back-extrapolate that future lock to the snapshot block.
- Impact: An attacker can wait until a proposal is active, lock OLA after the snapshot, and still vote as if the voting power existed at the snapshot. This bypasses the governor’s snapshot protection and allows late vote acquisition/manipulation.

## Active guard permits unchecked Safe calls

- Location: `governance/audits/internal10/analysis/contracts/GuardCM-flatten.sol` : `checkTransaction`
- Mechanism: While the guard is active, it only rejects delegatecalls, self-calls, and validates `schedule` / `scheduleBatch` calls sent to the timelock. Calls to any other target are allowed without `_verifyData()`, and calls to the timelock using selectors other than `schedule` / `scheduleBatch` are also allowed unchecked.
- Impact: A compromised or colluding community multisig threshold can bypass the target-selector allowlist by calling arbitrary non-timelock contracts directly. If the multisig has timelock roles such as `CANCELLER_ROLE`, it can also call unchecked timelock functions like `cancel(bytes32)` and block queued governance operations.

## Revoked buOLA locks can become permanently unwithdrawable

- Location: `governance/audits/internal/analysis/contracts/buOLA-flatten.sol` : `revoke`, `withdraw`
- Mechanism: `revoke()` stores `amountReleased = _releasableAmount(...)`, but `_releasableAmount()` returns only the currently claimable delta, not the cumulative released amount. After partial withdrawals this overwrites accounting and makes `withdraw()` compute an excessive burn amount, causing the later token transfer to fail. If revoke happens before any vesting step, `amountReleased` is zero and `withdraw()` reverts before reaching the burn/cleanup branch.
- Impact: The owner can accidentally or maliciously brick revoked accounts. Users may be unable to withdraw vested tokens, unvested tokens may never be burned, and buOLA supply/accounting can remain permanently stale.

