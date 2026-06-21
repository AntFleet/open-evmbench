# Audit: 2026-01-tempo-mpp-streams
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Zero `authorizedSigner` lets forged vouchers drain the full deposit
*(consensus, 6 of 6 reports)*
- Location: `contracts/TempoStreamChannel.sol` : `openChannel`, `_recoverSigner`, `settle` (and `close`)
- Mechanism: `openChannel` validates `payee != 0` and `deposit != 0` but never validates `authorizedSigner != address(0)`, and there is no setter to fix it later. `_recoverSigner` returns `address(0)` for any malformed signature (length ≠ 65), and `ecrecover` itself returns `address(0)` on an invalid `v`/recovery. The only auth gate in `settle` is `if (signer != channel.authorizedSigner) revert InvalidSigner();`. With `authorizedSigner == 0`, a junk/short signature recovers to `0`, the comparison `0 == 0` passes, and the unsigned voucher is accepted.
- Impact: For any channel opened with `authorizedSigner = address(0)` (a plausible "no delegate" misconfiguration the contract silently accepts), anyone — notably the payee, since funds route to `channel.payee` — can submit a fabricated voucher with `cumulativeAmount` up to `deposit` plus an invalid signature and drain the entire deposit. `close` is exploitable identically (same check).
- Reviewer disagreement: none.

## Unrestricted `initiateClose`/`finalize` lets anyone force-close any channel
*(consensus, 6 of 6 reports)*
- Location: `contracts/TempoStreamChannel.sol` : `initiateClose` (and `finalize`)
- Mechanism: `initiateClose` is `external` with no caller restriction — it only checks that the channel exists, is not finalized, and has no active grace period, then sets `gracePeriodEnd = block.timestamp + GRACE_PERIOD`. There is no cancel/reopen path and a second call reverts (`GracePeriodActive`), so once anyone triggers it the channel is permanently committed to closure. `finalize` is likewise unrestricted; after the grace period anyone can finalize, refunding `deposit - settled` to the payer and marking the channel finalized (after which `settle` reverts).
- Impact: Any third party with only a valid `channelId` can force any live channel onto a 1-hour shutdown path and then finalize it. The payee gets only the grace window to settle outstanding vouchers — and `finalize` can be called/front-run the instant `gracePeriodEnd` is reached to censor a pending `settle` — permanently dropping not-yet-settled vouchers. Griefing/DoS / value-loss, reachable by anyone.
- Reviewer disagreement: none.

## `deadline` parameter accepted but never enforced in `openChannel`
*(consensus, 3 of 6 reports)*
- Location: `contracts/TempoStreamChannel.sol` : `openChannel`
- Mechanism: `openChannel(..., uint256 deadline)` takes a `deadline` and the contract declares `error DeadlineExpired()`, but the body never compares `block.timestamp` against `deadline` and the error is never thrown anywhere. The parameter is dead.
- Impact: The transaction-expiry protection the API advertises does not exist. A queued/relayed/stuck-in-mempool `openChannel` can be mined arbitrarily late, pulling the payer's `deposit` via `safeTransferFrom` long after the payer's intent has lapsed. Lower-severity missing-validation issue.
- Reviewer disagreement: none.

## Deposit accounting credits requested amount, not received balance (fee-on-transfer/rebasing tokens)
*(consensus, 3 of 6 reports)*
- Location: `contracts/TempoStreamChannel.sol` : `openChannel`, `addDeposit` (consumed by `settle`, `finalize`, `close`)
- Mechanism: Both deposit paths call `safeTransferFrom` and then credit the requested `deposit`/`amount` directly, without measuring the contract's actual token-balance delta. For fee-on-transfer, rebasing, or otherwise non-standard ERC20s, `channel.deposit` can exceed the tokens actually held.
- Impact: For an accepted non-standard token a channel is overcredited and can consume tokens belonging to other channels using the same token (cross-channel insolvency), or later settlements/refunds revert for insufficient real balance; payees can be marked fully settled while receiving less than `delta` when outgoing transfers charge fees.
- Reviewer disagreement: 3 of 6 reports (the opus shots) defended the accounting as conservative/solvent ("per-channel payout sums to exactly `deposit - settled`," "token math is conservative, cross-channel draining isn't possible"), but those defenses assume standard ERC20s and do not address fee-on-transfer/rebasing tokens.

## Payer cooperative-close signature lacks domain separation (cross-deployment replay)
*(consensus, 2 of 6 reports)*
- Location: `contracts/TempoStreamChannel.sol` : `close`
- Mechanism: Unlike the EIP-712 voucher (which binds chainId and contract address), the payer's close authorization is a raw eth_sign over `keccak256(abi.encodePacked("CLOSE", channelId, cumulativeAmount))` — no chainId, no verifying-contract address, no nonce, no expiry. `channelId` derivation (`msg.sender, payee, token, block.timestamp, channelCounter`) also omits `address(this)`/`block.chainid`.
- Impact: The close signature is replayable against another deployment of the contract where an identically-derived `channelId` exists with the same payer (collision unlikely but possible — e.g., two fresh deployments at `channelCounter == 0` in the same block with the same parties/token). Hardening/replay gap rather than direct theft.
- Reviewer disagreement: none among the reports raising it.

## `close` ignores voucher `nonce`/`expiry`, so cooperative-close authorizations never expire and can be replayed
*(consensus, 2 of 6 reports)*
- Location: `contracts/TempoStreamChannel.sol` : `close`
- Mechanism: Unlike `settle`, `close` performs no `voucher.expiry` check and no `settledNonces` check, and never updates `settledNonces`. Both the voucher and the payer `CLOSE` signature are bound only to `(channelId, cumulativeAmount)`, so a once-produced cooperative-close pair stays valid indefinitely while the channel is unfinalized and cannot be revoked.
- Impact: After a close negotiation at some `cumulativeAmount`, if the parties instead keep streaming (payer tops up via `addDeposit` until `settled` reaches that amount), the stale close pair can be resubmitted later by the payee to force-finalize an in-use channel (refunding surplus to the payer); an already-expired voucher can be paired in since the expiry check is skipped. Terminates an active channel against current intent and forces a costly reopen — griefing/availability, token conservation still holds.
- Reviewer disagreement: none among the reports raising it.

## `close` lets the payer unilaterally finalize without payee consent
*(consensus, 2 of 6 reports)*
- Location: `contracts/TempoStreamChannel.sol` : `close`
- Mechanism: `close` is documented as cooperative but only verifies a voucher signature from `channel.authorizedSigner` and a close signature from `channel.payer`; it never requires `msg.sender == channel.payee` or a payee signature. Because `authorizedSigner` is payer-side state (often the payer itself or its delegate), the payer can produce both required signatures.
- Impact: A malicious payer can consume service, then immediately finalize at `voucher.cumulativeAmount == channel.settled` (or any amount ≥ already-settled), refunding all unsettled deposit to itself and blocking the payee from claiming higher-value but not-yet-submitted vouchers, since the channel is now finalized.
- Reviewer disagreement: none among the reports raising it. (The opus shots analyzed `close` but flagged only its replay/domain-separation weaknesses, not the missing payee-consent gate.)

## Minority findings

## Grace period does not actually bound settlement
*(minority, 1 of 6 reports)*
- Location: `contracts/TempoStreamChannel.sol` : `settle` (vs `initiateClose`/`finalize`)
- Mechanism: `initiateClose` records `gracePeriodEnd`, but `settle` only checks `channel.finalized` — it never rejects settlements after `gracePeriodEnd` has passed. Until someone successfully calls `finalize`, valid vouchers remain settleable indefinitely.
- Impact: A payee can settle after the intended dispute window has closed, including by front-running a `finalize` transaction, defeating the grace-period cutoff semantics.
- Reviewer disagreement: no other report explicitly defended this code path.

## Public `settle` + nonce advancement lets payer invalidate higher unsettled vouchers
*(minority, 1 of 6 reports)*
- Location: `contracts/TempoStreamChannel.sol` : `settle`
- Mechanism: `settle` is callable by anyone and advances `settledNonces` using the submitted voucher's nonce. A malicious payer or authorized signer can issue itself a higher-nonce, lower-cumulative voucher and settle it publicly, after which an earlier higher-cumulative voucher held by the payee fails with `NonceTooLow`.
- Impact: After the payee has delivered service against an unsettled voucher, the payer can front-run/preempt settlement with a low-value higher-nonce voucher; the payee receives only the small delta and permanently loses the ability to claim the earlier larger voucher.
- Reviewer disagreement: no other report explicitly defended this code path.

---

*Reconciliation: 9 distinct findings identified across the 6 input reports (by code path + root cause); 9 findings emitted (7 consensus, 2 minority). No findings dropped.*

