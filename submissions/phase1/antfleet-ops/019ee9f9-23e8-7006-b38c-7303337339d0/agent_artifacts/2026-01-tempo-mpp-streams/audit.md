# Audit: 2026-01-tempo-mpp-streams

# Security Audit: `TempoStreamChannel`

Findings below are ordered by severity. Only exploitable logic and accounting flaws are included.

---

## Zero `authorizedSigner` bypasses signature verification

- **Location:** `TempoStreamChannel.sol` : `openChannel`, `settle`, `close`
- **Mechanism:** `openChannel` never rejects `authorizedSigner == address(0)`. In `settle` and `close`, signer validation is `signer != channel.authorizedSigner` after `ecrecover`. On invalid or malformed signatures, `ecrecover` returns `address(0)`. When `authorizedSigner` is zero, that check passes with any garbage 65-byte signature—no valid ECDSA signature is required.
- **Impact:** For any channel opened with a zero authorized signer, the payee (or anyone calling `settle`) can drain the channel up to `deposit - settled` with a forged signature. Funds are sent to `channel.payee`. This is critical if a UI bug, misconfiguration, or malicious payee tricks the payer into opening a channel with `authorizedSigner = address(0)`.

```solidity
// settle — no require(authorizedSigner != address(0)) or require(signer != address(0))
address signer = _recoverSigner(digest, signature);
if (signer != channel.authorizedSigner) revert InvalidSigner();
```

---

## Unauthorized `initiateClose` forces closure timeline

- **Location:** `TempoStreamChannel.sol` : `initiateClose`
- **Mechanism:** `initiateClose` has no caller check (`msg.sender` is never compared to `payer` or `payee`). Any third party can start the grace timer on any open channel. After `GRACE_PERIOD`, anyone may call `finalize` and refund unsettled funds to the payer.
- **Impact:** A griefer or payer-aligned party can unilaterally start the 1-hour close clock. If the payee does not settle in time (or loses a race at `finalize`), legitimately owed voucher amounts are refunded to the payer instead of paid to the payee. This is a permissionless griefing / fund-loss path for the payee.

```solidity
function initiateClose(bytes32 channelId) external {
    // no access control — any address may call
    channel.gracePeriodEnd = block.timestamp + GRACE_PERIOD;
}
```

---

## `settle` remains callable after grace period until `finalize`

- **Location:** `TempoStreamChannel.sol` : `settle` (missing grace/finalize gating)
- **Mechanism:** `settle` only checks `!channel.finalized`. It does not read `gracePeriodEnd`. After `initiateClose`, the grace period only gates `finalize` (minimum wait), not `settle` (maximum window). Vouchers can still be settled indefinitely after grace ends, as long as the channel is not finalized and `voucher.expiry` has not passed.
- **Impact:** Payers who expect the grace period to cap the payee’s settlement window are misled. A payee can settle long after grace expires (e.g., vouchers with far-future `expiry`) until someone calls `finalize`. Conversely, this also means the payee is not actually cut off at grace end—they are cut off only when `finalize` executes, which leads to the race below.

---

## `finalize` vs `settle` race at channel close

- **Location:** `TempoStreamChannel.sol` : `finalize`, `settle`
- **Mechanism:** Once `block.timestamp >= gracePeriodEnd`, `finalize` is permissionless and sets `finalized = true` before refunds. `settle` does not check grace state. In the same block (or competing transactions), `finalize` and `settle` can race; the one that executes first wins. `settle` after `finalize` reverts with `ChannelAlreadyFinalized`.
- **Impact:** After grace ends, a payer (or MEV searcher) can front-run the payee’s final `settle` with `finalize`, causing unsettled voucher value to be refunded to the payer. The payee loses payment for services already rendered if vouchers were not yet submitted on-chain.

---

## Fee-on-transfer / deflationary token accounting mismatch

- **Location:** `TempoStreamChannel.sol` : `openChannel`, `addDeposit`, `settle`, `finalize`, `close`
- **Mechanism:** `channel.deposit` is incremented by the nominal `amount` passed to `safeTransferFrom`, not by measuring `balanceOf(address(this))` before and after. All channels sharing a token commingle balances in one contract pool with no per-channel token segregation.
- **Impact:** With fee-on-transfer or deflationary tokens, actual tokens received can be less than recorded `deposit`. A channel can settle or finalize refunds based on inflated accounting, draining tokens belonging to other channels (cross-channel insolvency). Conversely, `settle`/`finalize` can revert when the contract’s real balance is insufficient, bricking channels (DoS).

```solidity
token.safeTransferFrom(msg.sender, address(this), deposit);
channels[channelId] = Channel({ ..., deposit: deposit, ... }); // credits nominal amount
```

---

## `close` omits voucher nonce and expiry checks

- **Location:** `TempoStreamChannel.sol` : `close`
- **Mechanism:** Unlike `settle`, `close` does not enforce `voucher.nonce > settledNonces[channelId]` or `block.timestamp <= voucher.expiry`. It also does not update `channel.settled` or `settledNonces`. Cooperative close relies only on the authorized-signer EIP-712 voucher signature and the payer’s `"CLOSE"` personal_sign over `(channelId, cumulativeAmount)`.
- **Impact:** This is mostly intentional for cooperative shutdown, but it creates asymmetric rules: an expired voucher cannot be used in `settle` but can be used in `close` if the payer signs. A payer who signs a close message for `cumulativeAmount` without binding `nonce`/`expiry` could be induced to close on an older or different voucher than intended if multiple vouchers share the same cumulative amount. More importantly, if `settle` was partially executed, `close` can still finalize using a voucher whose nonce was already “superseded” off-chain—on-chain this is usually safe due to `delta = cumulativeAmount - channel.settled`, but the lack of nonce monotonicity in `close` is a footgun for integrators and weakens replay semantics relative to `settle`.

---

## `close` uses weaker payment bound than `settle`

- **Location:** `TempoStreamChannel.sol` : `close`
- **Mechanism:** `settle` requires `delta <= channel.deposit - channel.settled`. `close` only checks `delta > 0 && delta <= channel.deposit` (against total deposit, not remaining liability). Total outbound amounts are partly constrained because `payerRefund = channel.deposit - voucher.cumulativeAmount` reverts on underflow when `cumulativeAmount > deposit`, but the per-leg checks are inconsistent.
- **Impact:** Not directly exploitable for over-payment when `cumulativeAmount <= deposit` (total outflows still sum to `deposit - settled`), but the inconsistent guard is fragile under future edits and can mask integration mistakes. Relies on Solidity 0.8 underflow on `payerRefund` rather than an explicit `InsufficientDeposit`-style check.

---

## `ecrecover` wrapper lacks robust signature validation

- **Location:** `TempoStreamChannel.sol` : `_recoverSigner`
- **Mechanism:** Custom recovery does not reject EIP-2 malleable signatures (high-`s`), does not normalize `v`, and does not explicitly reject `address(0)` as a recovered signer except indirectly via the `authorizedSigner` comparison. OpenZeppelin’s `ECDSA.recover` enforces these checks.
- **Impact:** Limited direct theft because `settle` nonce tracking blocks replay of the same voucher with a malleated signature. Risk is mostly defense-in-depth and composability: malleable signatures, edge-case `v` values, and the zero-signer issue above. Not a standalone critical finding except in combination with `authorizedSigner == address(0)`.

---

## Unused `deadline` in `openChannel`

- **Location:** `TempoStreamChannel.sol` : `openChannel`
- **Mechanism:** `deadline` is accepted as a parameter and `DeadlineExpired` is defined, but the function never checks `block.timestamp <= deadline`.
- **Impact:** Transactions can be executed later than the payer intended (e.g., stale mempool txs), opening channels under outdated economic conditions. Lower severity; logic error in intended slippage/time protection rather than direct theft.

---

# Summary

| Severity | Count | Primary issues |
|----------|-------|----------------|
| Critical | 1 | Zero `authorizedSigner` → signature bypass |
| High/Medium | 4 | Permissionless `initiateClose`, grace/settle/finalize race, fee-on-transfer insolvency |
| Low/Medium | 3 | `close` nonce/expiry asymmetry, weak `close` bounds, `ecrecover` hardening |

**Recommended fixes (guidance only):**
1. `require(authorizedSigner != address(0))` and `require(signer != address(0))` in `settle`/`close`.
2. Restrict `initiateClose` to `payer` or `payee` (or both).
3. After `gracePeriodEnd`, either block `settle` or clearly document that only `finalize` ends the settlement window; consider restricting who may `finalize`.
4. Use balance-delta accounting for deposits, or document/enforce a token allowlist excluding fee-on-transfer tokens.
5. Align `close` with `settle` on nonce/expiry, or bind payer’s close signature to `nonce` and `expiry`.

