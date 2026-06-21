# Audit: 2024-05-olas
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

I merged all six reports (M = 6: opus‑4‑8 ×3, gpt‑5.5 ×3). I identified **10 distinct findings** by code path + root cause and all 10 appear below (8 consensus, 2 minority).

## Consensus findings

## buOLA revoke of an unvested lock bricks `withdraw` and strands OLA
*(consensus, 5 of 6 reports)*
- Location: `buOLA-flatten.sol` : `revoke` / `withdraw` (the `amount == 0` → `LockNotExpired` revert path) and `_releasableAmount`
- Mechanism: `revoke` sets `amountReleased = _releasableAmount(...)` and `end = 0`. When revoke happens before any step matures, `_releasableAmount` returns 0, so `amountReleased` stays 0 while `amountLocked` stays the full deposit. `withdraw` recomputes `amount = _releasableAmount(...) = 0` and hits `if (amount == 0) revert LockNotExpired(...)` *before* reaching the `else` branch that burns the revoked tokens and clears storage — so the burn and supply update are never executed.
- Impact: The full locked OLA is neither returned, burned, nor recoverable (no admin sweep exists) — frozen forever; `supply`/`balanceOf`/`totalSupply()` overstate real backing; `amountLocked` never returns to 0 so the account can never be re‑locked. Triggered by a routine early revocation.
- Reviewer disagreement (if any): none.

## buOLA revoke after a partial withdrawal double‑counts withdrawn tokens (over‑burn / withdraw revert)
*(consensus, 3 of 6 reports)*
- Location: `buOLA-flatten.sol` : `revoke` (`amountReleased = uint96(amountRelease); end = 0`) interacting with `withdraw` (`amountBurn = amountLocked − amountReleased`) and `_releasableAmount`
- Mechanism: `amountReleased` is overloaded. During normal vesting `withdraw` keeps it as the **cumulative** amount paid out, but `revoke` overwrites it with the **incremental** currently‑releasable remainder (`vested_now − alreadyWithdrawn`). Afterward `withdraw` computes `amountBurn = amountLocked − amountReleased = (amountLocked − vested_now) + alreadyWithdrawn`, double‑counting the already‑withdrawn tokens, while the contract only holds `amountLocked − withdrawn`.
- Impact: For any prior withdrawal > 0, every future `withdraw` reverts (on `burn` or `transfer`) — the user's vested‑but‑unclaimed tokens are permanently stuck and the intended burn never happens. When this is the only/large locker, `supply -= amountBurn` underflows in the `unchecked` block, corrupting `supply` to near‑max and making buOLA insolvent so other lockers' withdrawals revert. Worked example: 100 OLA / 10 steps, withdraw 30 at step 3, revoke at step 5 → tries to burn 80 and remove 100 instead of 50/70.
- Reviewer disagreement (if any): none.

## buOLA `_releasableAmount` multiplies in `uint96` inside an `unchecked` block (silent overflow)
*(consensus, 3 of 6 reports)*
- Location: `buOLA-flatten.sol` : `_releasableAmount` (else branch: `amount = uint256(lockedBalance.amountLocked * releasedSteps / numSteps); amount -= uint256(amountReleased);`)
- Mechanism: `amountLocked` (`uint96`) `* releasedSteps` (`uint32`) is evaluated in `uint96` *before* the `uint256` cast, inside `unchecked`. The deposit bound only caps a single lock at `2^96−1`, and `releasedSteps` reaches 9, so once a lock approaches `2^96/9 ≈ 8.8e27` the product wraps mod `2^96`; the wrapped small product then makes the subsequent unchecked `amount -= amountReleased` underflow toward `2^256`.
- Impact: A very large lock gets a wrong releasable amount — withdrawals either revert (funds frozen) or, via underflow + `uint96` truncation, corrupt `amountReleased`/`supply` and over‑release. Latent/far‑future (reachable as 2%/yr inflation grows supply), roughly halving the contract's documented ~220‑year safety margin. Fix: `uint256(amountLocked) * releasedSteps / numSteps`.
- Reviewer disagreement (if any): none.

## Permissionless buOLA `createLockFor` enables dust‑lock DoS on a vesting recipient
*(consensus, 2 of 6 reports)*
- Location: `buOLA-flatten.sol` : `createLockFor`
- Mechanism: `createLockFor` is permissionless and writes the first `LockedBalance` for any nonzero `account`; later creation reverts while `amountLocked > 0`. An attacker pre‑empts a legitimate allocation with a dust lock and attacker‑chosen `numSteps` (e.g. 10); round‑down releases mean nothing is releasable until final maturity.
- Impact: Blocks the recipient from receiving/creating the intended lock for up to 10 years for the cost of dust OLA; compounds with the revoke‑unvested bug (if the owner revokes the dust lock pre‑vesting, `amountLocked` stays uncleared forever).
- Reviewer disagreement (if any): none.

## Permissionless VotingEscrow `createLockFor` enables dust‑lock DoS on a victim
*(consensus, 2 of 6 reports)*
- Location: `VotingEscrow-flatten.sol` : `createLockFor` / `_createLockFor`
- Mechanism: `createLockFor` lets any caller create the first lock for any nonzero `account` with the caller's tokens; once `mapLockedBalances[account].amount > 0`, `_createLockFor` rejects further creation, so the victim can only add to / extend the attacker‑chosen lock, not replace or shorten it. A 1‑wei max‑duration lock costs the attacker dust.
- Impact: An attacker forces a victim into an unwanted lock (up to 4 years), blocking them from choosing their own escrow terms. Precondition: victim has no existing lock.
- Reviewer disagreement (if any): three opus reviewers cleared VotingEscrow as a faithful, well‑bounded Curve port (no arithmetic/cast/reentrancy issue), but addressed casts/accounting rather than this permissionless‑creation design DoS.

## Short calldata bypasses selector authorization in GuardCM / bridge verifier
*(consensus, 2 of 6 reports)*
- Location: `GuardCM-flatten.sol` & `ProcessBridgedDataArbitrum-flatten.sol` : `VerifyData._verifyData` (via `_verifySchedule` / `processBridgeData`)
- Mechanism: `_verifyData` derives the selector as `bytes4(data)` without requiring `data.length >= 4`; Solidity zero‑pads 1–3‑byte calldata, so sub‑4‑byte calldata can match an allowlisted selector whose trailing bytes are zero. The outer schedule length is checked, but each inner `callDatas[i]` / bridged `targetPayload` length is not.
- Impact: A guarded/compromised multisig can schedule a call that passes the target‑selector allowlist while delivering sub‑4‑byte calldata, invoking the target's fallback/receive path instead of the intended function. Precondition: an allowlisted selector with zero trailing bytes and a target with security‑relevant fallback/receive behavior.
- Reviewer disagreement (if any): opus shot 1 noted the guard's schedule/bridge verification paths are "length‑checked before slicing," but that refers to outer‑payload slicing, not the `bytes4(data)` selector derivation.

## GuardCM whitelist ignores scheduled ETH value
*(consensus, 2 of 6 reports)*
- Location: `GuardCM-flatten.sol` : `_verifySchedule` / `checkTransaction`
- Mechanism: The guard decodes scheduled timelock operations but authorizes only `(target, selector, chainId)`, discarding the `value` field of `schedule` and the `values` array of `scheduleBatch`.
- Impact: If the timelock holds ETH and a whitelisted payable/bridge target exists, the guarded multisig can pair an allowed selector with arbitrary ETH value, moving ETH out of the timelock while passing guard checks.
- Reviewer disagreement (if any): none.

## Arbitrum bridge verifier ignores retryable value / fee / refund‑address parameters
*(consensus, 2 of 6 reports)*
- Location: `ProcessBridgedDataArbitrum-flatten.sol` : `processBridgeData` (and the bridge path of GuardCM's verifier)
- Mechanism: The verifier decodes `createRetryableTicket` / `unsafeCreateRetryableTicket` but checks only `targetAddress` and the selector inside `targetPayload`, ignoring call value, gas params, `excessFeeRefundAddress` and `callValueRefundAddress`.
- Impact: A guarded multisig passes bridge target‑selector verification while setting attacker‑controlled refund recipients / retryable value; if the timelock funds the bridge call, ETH intended for execution/refunds can be redirected.
- Reviewer disagreement (if any): none.

## Minority findings

## buOLA `revoke` performs no burn or supply reduction itself (misleading `Revoke` event)
*(minority, 1 of 6 reports)*
- Location: `buOLA-flatten.sol` : `revoke`
- Mechanism: `revoke` is documented "Revoke and burn all non‑matured tokens" and emits `Revoke(account, amountLocked − amountRelease, ...)`, but it only rewrites the `LockedBalance` (`amountReleased`, `end = 0`); it never calls `IOLA.burn` or updates `supply`. The burn is deferred entirely to the user's later `withdraw`, and the owner has no way to force it.
- Impact: Even apart from the revert cases, `supply`/`totalSupply()` diverge from real backing and the to‑be‑burned OLA sits idle indefinitely if the user never withdraws; the emitted event falsely signals destruction, corrupting downstream logic that trusts `buOLA.totalSupply()`.
- Reviewer disagreement (if any): none (no report defended this path; the related zero‑vested freezing is the consensus finding above).

## OLA.mint silently succeeds (no‑op) when amount exceeds the inflation cap
*(minority, 1 of 6 reports)* *(conflicting reviews: 1 of 6 reports defended this code path)*
- Location: `OLA-flatten.sol` : `mint` (with `inflationControl` / `inflationRemainder`)
- Mechanism: `mint` is `if (inflationControl(amount)) { _mint(account, amount); }`; when `amount > inflationRemainder()` the condition is false and `mint` returns successfully without minting and without reverting. A dedicated error `MintRejectedByInflationPolicy(uint256)` is declared in `IErrors` but unused, indicating the intended behavior was to revert.
- Impact: A privileged minter (tokenomics/treasury/dispenser) that treats a non‑reverting `mint()` as success keeps its own accounting (bonds/rewards/distributions) as if supply grew when it did not, becoming under‑collateralized; drift accumulates exactly at the supply‑cap boundary, precisely when a mint is most likely to graze the cap.
- Reviewer disagreement (if any): opus shot 1 explicitly called this out and judged it "not a security issue" (a silent no‑op rather than a revert); opus shot 3 also reviewed OLA and found no genuine vuln beyond owner‑trust assumptions.

---

**Reconciliation:** distinct input findings = 10; findings in output = 10 (8 consensus + 2 minority). No findings dropped.

