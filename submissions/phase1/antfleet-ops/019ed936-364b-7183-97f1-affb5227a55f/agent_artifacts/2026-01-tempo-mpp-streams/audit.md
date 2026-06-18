# Audit: 2026-01-tempo-mpp-streams

Here is the merged report.

---

# TempoStreamChannel.sol — Merged Security Audit (Reviewer A + Reviewer B)

## Consensus findings

## Payer can unilaterally finalize the cooperative `close` with no payee consent
*(consensus)*
- Location: contracts/TempoStreamChannel.sol : `close(Voucher, signature, payerSignature)` (lines ~388–442)
- Mechanism: `close` is described as "cooperative" but authenticates only the **payer side**. It verifies (a) a voucher signed by `channel.authorizedSigner` and (b) a `payerSignature` over `keccak256("CLOSE", channelId, cumulativeAmount)` from `channel.payer`. Both keys are controlled by the paying party (the payer is, or delegates, the `authorizedSigner`), so the payer can mint a brand-new voucher for any `cumulativeAmount >= channel.settled` (including `== settled`, giving `delta == 0`), sign the matching close hash, and call `close`. There is no payee signature, no `msg.sender == payee` check, no nonce check, no expiry check, and no requirement that the closing amount reflect the highest voucher the payee actually holds. The function sets `channel.finalized = true`, pays only the supplied cumulative amount, and refunds the remainder to the payer via `payerRefund = deposit - cumulativeAmount`. Critically, this path bypasses `initiateClose`/`GRACE_PERIOD` entirely (no `gracePeriodEnd` check), removing the only window the payee has to settle pending vouchers.
- Impact: A malicious payer drains back all not-yet-on-chain-settled deposit at will, denying the payee payment for services already rendered. Example: deposit = 100, `settled` = 0, payee holds off-chain vouchers worth 90 of delivered LLM inference; payer self-signs a voucher with `cumulativeAmount = 0` (or any low value), signs the close hash, and calls `close` — payee receives 0, payer is refunded 100, and finalization makes the payee's 90-value vouchers permanently unsettleable. This defeats the core payment guarantee of the channel. Preconditions (payer controls the authorized signer) are an intended configuration. A correct unidirectional channel must let the *recipient* claim via the latest voucher and only allow the payer to close through the timeout/grace-period path, never instantly and unilaterally.

## No zero-address validation on `authorizedSigner` enables a full voucher-signature bypass
*(consensus)*
- Location: contracts/TempoStreamChannel.sol : `openChannel(...)` (lines ~219–260), `_recoverSigner(...)` (lines ~182–200), and the signer checks in `settle` (lines ~292–323) / `close`
- Mechanism: `openChannel` never checks `authorizedSigner != address(0)` (it only validates `payee` and `deposit`). `_recoverSigner` returns `address(0)` whenever the signature length isn't 65, and `ecrecover` itself returns `address(0)` for malformed `v`/`s`. In `settle`, the only authorization gate is `if (signer != channel.authorizedSigner) revert InvalidSigner();`. If a channel was opened with `authorizedSigner == address(0)`, submitting a deliberately invalid signature makes `signer == address(0) == channel.authorizedSigner`, passing the check. The same `address(0)` match also bypasses both signature checks in `close`. Additionally, `_recoverSigner` performs no EIP-2 low-`s`/`v` normalization, so signatures are malleable (replay in `settle` is independently blocked by the nonce).
- Impact: For any channel created with `authorizedSigner == address(0)` (a plausible misconfiguration, or a payer tricked into it, since nothing prevents it), anyone can craft arbitrary vouchers (any `cumulativeAmount` up to `deposit`, any nonce/expiry) with a junk signature and call `settle`, draining the entire deposit to the payee with no valid signature ever produced. Fix: reject `authorizedSigner == address(0)` in `openChannel` and treat `signer == address(0)` as an invalid signature.

## Missing access control on `initiateClose` (and `finalize`) — any third party can force-close any channel
*(consensus)*
- Location: contracts/TempoStreamChannel.sol : `initiateClose(bytes32 channelId)` (lines ~342–377) and `finalize(bytes32 channelId)` (lines ~350–377)
- Mechanism: `initiateClose` is `external` with no caller restriction — it only checks that the channel exists, isn't finalized, and has `gracePeriodEnd == 0`. Any address (not just payer or payee) can set `gracePeriodEnd` and start the grace-period countdown on an arbitrary active channel. `finalize` is likewise callable by anyone after the grace period; it refunds the remaining deposit and permanently marks the channel finalized. While `finalize`'s fund distribution is correct (settled already paid to payee, remainder refunded to payer), the unrestricted *initiation* forces the closure lifecycle on any live streaming channel.
- Impact: Denial-of-service / griefing against active payment channels. An attacker can call `initiateClose` on every open channel, forcing each into the (1-hour) countdown after which it can be finalized and refunded, prematurely terminating ongoing metered-service streams. The payee is not directly robbed (they can still `settle` their latest voucher during the grace window), but service is disrupted and the payee must spend gas to react within the window; if the payee misses the grace window, voucher settlement becomes impossible after finalization. `initiateClose` should be restricted to `channel.payer` / `channel.payee`.

---

## Additional findings (single-reviewer)

## Higher-nonce low-value vouchers can permanently invalidate unpaid higher-value vouchers
*(Reviewer B only)*
- Location: contracts/TempoStreamChannel.sol : `settle` (lines ~292–323)
- Mechanism: `settle` accepts any voucher whose nonce is greater than `settledNonces[channelId]`, even if `cumulativeAmount` is only equal to (or lower than) the already-settled amount, and it then advances `settledNonces` globally. Because `settle` is callable by anyone, the payer or authorized signer can submit a zero-delta or low-value higher-nonce voucher before the payee settles an earlier, higher-value voucher.
- Impact: A malicious payer can receive service after handing the payee a valid unpaid voucher, then settle a higher-nonce lower-value voucher so the payee's voucher reverts with `NonceTooLow`, denying payment for delivered service. Preconditions: the payee does not settle every voucher immediately, and the payer controls or can direct the authorized signer.

## Pooled token balance with nominal-amount accounting — fee-on-transfer / deflationary tokens leave channels under-collateralized and cross-drainable
*(Reviewer A only)*
- Location: contracts/TempoStreamChannel.sol : `openChannel` / `addDeposit` (`channel.deposit += amount` / `deposit` recorded as the requested amount after `safeTransferFrom`, lines ~240–290)
- Mechanism: All channels share a single contract token balance, but each channel's `deposit` is credited with the **nominal** amount passed in, not the amount actually received; the contract never measures `balanceOf` before/after the transfer. For a fee-on-transfer, deflationary, or rebasing token, the contract receives less than `deposit`, so the sum of all channels' `(deposit - settled)` exceeds the real balance. Per-channel payout bounds (`settle`, `finalize`, `close`) are checked only against the channel's own recorded `deposit`, so an over-credited channel's full payout draws from the shared pool — paying out using other channels' tokens.
- Impact: With a fee-on-transfer/rebasing TIP-20 token, a channel can be settled/refunded for more than its real backing, draining funds belonging to other channels and ultimately leaving the last claimants unable to withdraw (transfers revert on insufficient balance). Precondition: a non-standard token is used (the protocol intends standard stablecoins, so severity is conditional). Fix: credit `deposit` based on the actual measured balance delta, or restrict to a vetted token allowlist.

---

**Merge notes:** A#1↔B#3 (unilateral close), A#2↔B#1 (zero signer), and A#3↔B#4 (unrestricted force-close) each describe the same root cause and code path and were merged into the three consensus findings above, keeping the most specific line ranges and details from both sides. B's nonce/voucher-invalidation finding and A's fee-on-transfer accounting finding had no counterpart in the other report and are listed as single-reviewer. (Note: I attempted to also save this to `/tmp/merged-audit.md` but the write wasn't permitted — let me know if you'd like it written to a file in your workspace.)

