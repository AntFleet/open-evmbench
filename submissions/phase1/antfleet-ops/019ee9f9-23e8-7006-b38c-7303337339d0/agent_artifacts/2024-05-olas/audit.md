# Audit: 2024-05-olas

# Open EVMBench Detect Audit Report — Autonolas Governance (2024-05-olas)

## GuardCM whitelist bypass on direct Safe transactions

- Location: `GuardCM.sol` : `checkTransaction`
- Mechanism: When the guard is active (`paused == 1`), `checkTransaction` only inspects calls whose destination is the timelock (`to == owner`) and whose selector is `schedule` or `scheduleBatch`. Calls to the timelock with any other selector are allowed without review, and calls to every other address (except the multisig itself) pass with no target/selector/chain-id checks. The intended allowlist in `mapAllowedTargetSelectorChainIds` and bridge verification in `_verifySchedule` therefore apply only to timelock scheduling paths, not to direct Safe executions.
- Impact: A compromised community multisig (or any CM signer coalition) can bypass the entire guard by calling arbitrary contracts directly—e.g., bridge mediators with `unsafeCreateRetryableTicket` / `createRetryableTicket`, token contracts, or protocol admin functions—without triggering `_verifyData` or `processBridgeData`. This defeats the core security purpose of the guard.

## GuardCM bridge verification bypass via direct bridge-mediator calls

- Location: `GuardCM.sol` : `checkTransaction` / `_verifySchedule`
- Mechanism: Bridge payload validation is only reached when the CM schedules through the timelock (`to == owner`, `schedule`/`scheduleBatch`) and the scheduled target is registered in `mapBridgeMediatorL1BridgeParams`, which triggers a `delegatecall` to the L2 verifier. A direct Safe transaction to an L1 bridge mediator is not covered by that path at all (see finding above), so `ProcessBridgedDataArbitrum.processBridgeData` is never invoked.
- Impact: An attacker controlling the CM can submit unauthorized cross-chain messages to Arbitrum (or other configured L2s) by calling the L1 bridge mediator directly with arbitrary retryable-ticket calldata, completely circumventing the authorized `(target, selector, chainId)` mapping that the guard is meant to enforce.

## GuardCM `pause()` fully disables all transaction checks

- Location: `GuardCM.sol` : `pause` / `checkTransaction`
- Mechanism: When `paused == 2`, `checkTransaction` returns immediately without enforcing delegatecall prohibition, self-call prohibition, schedule validation, or any other check. The multisig may call `pause()` whenever `IGovernor(governor).state(governorCheckProposalId)` returns `Defeated`; the timelock owner can pause unconditionally.
- Impact: Once paused, the CM operates with no guard restrictions whatsoever (including delegatecalls). If CM keys are compromised, or if the hard-coded `governorCheckProposalId` is or becomes `Defeated`, an attacker can permanently operate the CM outside the allowlist until the timelock explicitly calls `unpause()`.

## GuardCM `delegatecall` to L2 verifier can mutate guard storage

- Location: `GuardCM.sol` : `_verifySchedule`
- Mechanism: For bridged schedule targets, the guard executes `bridgeParams.verifierL2.delegatecall(...)` during `checkTransaction`. `delegatecall` runs the verifier’s bytecode in `GuardCM`’s storage context, so any write in the verifier (or a malicious replacement set via `setBridgeMediatorL1BridgeParams`) can overwrite `GuardCM` state slots, including `mapAllowedTargetSelectorChainIds`, `governor`, `paused`, and `mapBridgeMediatorL1BridgeParams`. State changes persist after the guard hook returns.
- Impact: A malicious or buggy verifier contract can corrupt or disable guard configuration during a legitimate-looking schedule check—e.g., widening the allowlist, forcing `paused = 2`, or repointing the governor—leading to unauthorized CM actions or permanent guard bypass.

## VotingEscrow checkpoint limited to 255 weeks corrupts voting power

- Location: `VotingEscrow.sol` : `_checkpoint`
- Mechanism: Global checkpointing advances time in a hard-coded loop of at most 255 weekly steps. If more than ~5 years elapse since the last global point without a successful full catch-up (the contract’s own comments acknowledge this scenario), the loop exits without bringing `lastPoint` to `block.timestamp`. Subsequent `getPastTotalSupply`, `totalSupplyLocked`, and quorum calculations use stale bias/slope state.
- Impact: After a long inactivity gap, global voting-power accounting diverges from reality. Governance quorum and vote totals can be wrong—either inflating or deflating aggregate voting power—allowing proposals to pass or fail contrary to actual locked-token economics. Token withdrawals still work, but governance integrity is broken until manual recovery.

## VotingEscrow negative bias/slope clamping corrupts vote accounting

- Location: `VotingEscrow.sol` : `_checkpoint`
- Mechanism: During weekly iteration and user balance updates, if computed `lastPoint.bias` or `lastPoint.slope` becomes negative, the contract silently clamps the value to zero instead of reverting. Internal fuzzing artifacts in the same audit bundle (`VotingEscrowFuzzing`, `VotingEscrowVerySimple`) show Echidna reaching these branches with concrete counterexamples; the production comment claiming the fuzzer “didn’t find available real combinations” is incorrect.
- Impact: Clamping hides accounting errors caused by integer rounding and slope-change scheduling. Global and per-user voting curves no longer sum correctly, so `getVotes`, `getPastVotes`, and `getPastTotalSupply` can over- or under-state power. An attacker can manipulate lock timing and amounts to exploit rounding edge cases and gain disproportionate governance influence or disrupt quorum.

## OLA `mint` silently succeeds when inflation cap is exceeded

- Location: `OLA.sol` : `mint`
- Mechanism: `mint` calls `_mint` only when `inflationControl(amount)` returns true; otherwise it returns without reverting and without emitting a failure event. Callers receive no on-chain signal that zero tokens were minted.
- Impact: Integrators, treasuries, or automated inflation scripts can believe inflation occurred when it did not, causing treasury/accounting drift, failed downstream allocations, and operational security gaps. A malicious minter can also use this to grief dependent systems that do not verify balance deltas.

## OLA `changeMinter` allows setting the zero address

- Location: `OLA.sol` : `changeMinter`
- Mechanism: Unlike `changeOwner`, `changeMinter` does not validate `newMinter != address(0)`. The owner can set `minter` to `address(0)`, after which every `mint` call reverts with `ManagerOnly`.
- Impact: A single owner mistake (or malicious owner action) permanently bricks all future OLA inflation/minting with no recovery path inside the token contract, freezing protocol emissions.

## ProcessBridgedDataArbitrum does not validate the configured L2 bridge mediator

- Location: `ProcessBridgedDataArbitrum.sol` : `processBridgeData`
- Mechanism: The contract defines `WrongL2BridgeMediator` but never uses it. The `bridgeMediatorL2` argument is explicitly unused (`address,`), and verification only checks the `(targetAddress, targetPayload)` pair decoded from the retryable-ticket calldata against `mapAllowedTargetSelectorChainIds`. There is no binding between the configured mediator in `GuardCM.mapBridgeMediatorL1BridgeParams` and the actual L2 destination encoded in the ticket.
- Impact: When verification is reached via the schedule path, a CM can still craft retryable tickets whose L2 execution target/payload is allowlisted but whose routing does not match the intended L2 bridge mediator configuration, weakening defense-in-depth and enabling ambiguous or misrouted cross-chain operations if ticket fields are misunderstood or misconfigured. (Direct-call bypass remains the higher-severity path; see GuardCM findings above.)

---

**Scope note:** `GovernorOLA` and `Timelock` are thin wrappers over audited OpenZeppelin bases with no additional custom logic. Fuzzing harness contracts (`VotingEscrowFuzzing`, `buOLAFuzzing`, etc.) were used as evidence for production `VotingEscrow` issues but are not separately listed as deployable production targets.

