# Audit: 2024-05-olas

## Executor-to-admin takeover via self-scheduling batch reentrancy
- Location: `Timelock-flatten.sol` : `TimelockController.executeBatch`
- Mechanism: `executeBatch()` performs the batch’s external calls before the timelock marks the operation as consumed, and `_afterCall()` only checks `isOperationReady(id)` after those calls finish. That lets a batch call the timelock itself to first reduce the delay to zero, grant `PROPOSER_ROLE` to `address(this)`, and then `scheduleBatch()` the very same batch. Because readiness is validated only after the self-calls, an operation that was not scheduled or ready at entry can make itself ready mid-execution and still pass the post-check. This is the known OpenZeppelin `TimelockController` privilege-escalation flaw in this version.
- Impact: Any actor that can execute timelock operations, commonly anyone if `EXECUTOR_ROLE` is open or any granted executor otherwise, can take over the timelock, grant arbitrary roles, set delay to zero, and execute arbitrary governance actions without an approved proposal. This also compromises any `GovernorOLA` deployment that relies on this timelock.

## A single defeated proposal permanently disables the Safe guard
- Location: `GuardCM-flatten.sol` : `GuardCM.pause`
- Mechanism: the multisig can call `pause()` whenever one fixed `governorCheckProposalId` is merely in `Defeated` state. That state is too weak a liveness signal: it includes actively rejected proposals and proposals that just missed quorum, not only “governance is dead”. Once `paused` is set to `2`, `checkTransaction()` stops enforcing all guard restrictions until the timelock explicitly unpauses. A malicious or impatient multisig can therefore wait for, or help engineer, failure of the designated health-check proposal and use that failure as a full escape hatch.
- Impact: The community multisig can disable all target/selector checks and regain unrestricted Safe execution during normal governance conditions, bypassing the intended governance constraint model.

No other concrete exploitable vulnerabilities were confirmed in the supplied contracts beyond these two.

