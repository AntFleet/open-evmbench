# Audit: 2024-05-olas

I found two genuine security vulnerabilities.

## Voting Power Can Be Backdated After a Proposal Snapshot
- Location: `governance/audits/internal/analysis/contracts/VotingEscrow-flatten.sol` : `getPastVotes`
- Mechanism: `getPastVotes()` calls `_findPointByBlock()` for the user checkpoint, but it never verifies that the returned user point was created at or before the requested `blockNumber`. If an account has no checkpoint before the requested block, `_findPointByBlock()` still returns the account’s first checkpoint, even if that checkpoint is from a later block. `getPastVotes()` then extrapolates that later point backwards in time, increasing the bias because `blockTime < uPoint.ts`. As a result, tokens locked after a proposal snapshot are counted as if they were locked before the snapshot.
- Impact: An attacker can wait until a proposal is active, lock OLA after the snapshot block, and still vote with that newly-created voting power. The attacker’s votes are added to `forVotes`/`againstVotes`, while the quorum calculation for the snapshot does not include the newly locked supply, allowing governance outcomes to be manipulated.

## Guard Allows Multisig to Bypass Restrictions via Timelock Cancel
- Location: `governance/audits/internal10/analysis/contracts/GuardCM-flatten.sol` : `checkTransaction`
- Mechanism: The guard only validates calls to the timelock when the selector is `schedule` or `scheduleBatch`. Any other call to the timelock is allowed without target/selector validation. Since OpenZeppelin `TimelockController` grants `CANCELLER_ROLE` to proposers, a guarded community multisig that is configured as a proposer can call `cancel(bytes32)` directly through the timelock. The guard does not block or inspect this path.
- Impact: A malicious or compromised community multisig can cancel queued governance operations and deny execution of approved DAO proposals, bypassing the guard’s intended restriction model.

