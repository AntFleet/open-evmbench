# Audit: 2026-01-tempo-stablecoin-dex

Here is the merged report.

---

# Merged Security Audit — StablecoinDEX.sol

Two independent reviews (A: Claude, B: Codex) of the same codebase. `MockTIP20.sol` is a trivial test token with no flagged issues; all findings concern `StablecoinDEX.sol`.

## Consensus findings

## Unauthenticated drain via `emergencyWithdraw` (no balance check + `unchecked` underflow)
*(consensus)*
- Location: `StablecoinDEX.sol` : `emergencyWithdraw` / `_processWithdrawal` (the "INTERNAL WITHDRAWAL" section)
- Mechanism: `emergencyWithdraw(token, amount)` is `external` with **no access control and no input/balance validation** — it never checks `token != address(0)`, `amount != 0`, or `balances[msg.sender][token] >= amount`. It forwards directly into `_processWithdrawal`, which decrements both `balances[user][token]` and `totalDeposits[token]` inside an `unchecked` block and then performs `IERC20(token).safeTransfer(user, amount)`. Because the subtraction is `unchecked`, an `amount` larger than the caller's recorded balance **wraps around** to a near-`2^128` value instead of reverting. The unrelated `withdraw` function does check `balances[msg.sender][token] < amount`, but this "emergency" path skips it entirely.
- Impact: Any address can call `emergencyWithdraw(token, contractTokenBalance)` and transfer out the **entire token balance of the contract**, stealing every depositor's funds in a single transaction, regardless of their own recorded balance. As a bonus, the underflow leaves the attacker's recorded `balances` at ~`2^128`, so they can keep draining via the normal `withdraw` path. Preconditions: the DEX holds the target token and the transfer succeeds. Complete, permissionless loss of all funds — critical.

## Anyone can cancel anyone else's order (missing maker authorization)
*(consensus)*
- Location: `StablecoinDEX.sol` : `cancel` (calls `_cancelOrder`)
- Mechanism: `cancel(uint128 orderId)` only checks `order.maker == address(0)` (i.e. that the order exists). It never verifies `msg.sender == order.maker` before calling `_cancelOrder`. `_cancelOrder` then unlinks the order and refunds `order.remaining` base tokens back to the *original* maker's `available` balance and deletes the order. The refund goes to the rightful maker (so it is not direct theft), but the cancellation itself is attacker-controlled.
- Impact: Any user can cancel every open order on the book at will. This is a permissionless griefing / market-manipulation primitive: an attacker can wipe out all resting liquidity, force-close competitors' orders right before/after price-sensitive actions, and continuously deny makers the ability to keep orders live. Preconditions: the attacker knows or discovers an active `orderId` (IDs are sequential and exposed).

## Additional findings (single-reviewer)

## `fillOrder` rounds the quote payment down in the taker's favor, with no minimum fill
*(Reviewer A only)*
- Location: `StablecoinDEX.sol` : `fillOrder` — `uint256 quoteAmount = (uint256(amount) * uint256(order.price)) / 1e18;`
- Mechanism: The quote cost is computed with floor division (`/ 1e18`) and rounds **down**, in favor of the taker (the party paying quote and receiving base). `fillOrder` enforces only `amount != 0` and `amount <= remaining`; the `MIN_ORDER_SIZE` floor is applied solely in `placeOrder`, never to fills. A taker can split a fill into many tiny `amount` increments, each truncating up to nearly one full quote unit off the price. For a price just under parity (e.g. `0.99e18`), filling `amount = 2` yields `quoteAmount = floor(1.98) = 1` — paying 1 quote unit for ~2 units of value, ~50% underpayment per fill.
- Impact: A taker systematically underpays the maker. Each fill leaks at most ~1 quote unit, so extracting large value needs many transactions — but this contract targets a ~20,000 TPS, low-fee payment chain (Tempo), where high-frequency dust fills are economically realistic. Makers receive less quote than the stated order price, with the rounding bias always against them.

## CEI violation / reentrancy ordering in `withdraw` (and `deposit`)
*(Reviewer A only)*
- Location: `StablecoinDEX.sol` : `withdraw` (balance check → `safeTransfer` → `balances -= amount; totalDeposits -= amount`), and `deposit` (transfer before credit)
- Mechanism: `withdraw` performs the external `IERC20(token).safeTransfer(msg.sender, amount)` **before** decrementing `balances` and `totalDeposits`. TIP-20 / TIP-403 tokens (per this contract's own documentation) support compliance hooks/callbacks during transfer, so the recipient can re-enter while their on-chain balance is still un-decremented. There is no reentrancy guard anywhere in the contract.
- Impact: In the current code, Solidity 0.8 **checked** arithmetic on the post-transfer `balances -= amount` causes any re-entrant double-spend attempt (same function or cross-function via `placeOrder`/`withdraw`) to underflow and revert, so no fund-loss exploit is constructible today. Flagged as a latent vulnerability: the ordering is incorrect, relies entirely on checked math for safety, and any future change wrapping these subtractions in `unchecked` (as `_processWithdrawal` already does) or adding a hook-driven path would turn it into a live reentrancy drain. Fix: move state updates before the external call and/or add a `nonReentrant` guard.

## `MAX_PRICE_DEVIATION` declared but never enforced
*(Reviewer A only)*
- Location: `StablecoinDEX.sol` : `placeOrder` (constant `MAX_PRICE_DEVIATION`)
- Mechanism: `MAX_PRICE_DEVIATION` is declared but never referenced in `placeOrder`, so orders can rest at arbitrarily off-parity prices despite the documented 1% cap.
- Impact: Missing validation rather than a direct attack — each counterparty opts in to a price — but it breaks the contract's stated stablecoin-parity assumption and allows wildly off-peg resting orders.

## Filled orders leave stale linked-list pointers and corrupt later cancellations
*(Reviewer B only)*
- Location: `StablecoinDEX.sol` : `_removeFilledOrder`, `_cancelOrder`
- Mechanism: `_removeFilledOrder` unlinks a fully filled order from the list and zeroes `prev`, `next`, and `maker`, but leaves `baseToken`, `quoteToken`, `price`, `amount`, and `remaining` in storage. `_cancelOrder`, conversely, deletes only `maker`, `baseToken`, `quoteToken`, `price`, and `amount`, leaving `remaining`, `prev`, and `next` untouched. A cancelled order therefore retains stale linked-list pointers. Because order IDs are sequential and exposed, later cancellation/fill paths can operate around stale neighbor references and overwrite `orderHeads` or neighboring order pointers using data from an already-deleted order.
- Impact: Attackers can corrupt order-book linked lists by cancelling orders with stale pointers, causing active orders to become unreachable from `orderHeads` or causing traversal to skip valid liquidity. Preconditions: attacker can place/cancel orders in the affected pair and exploit the stale `prev`/`next` retained after deletion.

---

**Merge notes:**
- Both reports independently identified the two critical issues (`emergencyWithdraw` drain and the missing maker check in `cancel`), so those are consolidated as consensus findings, preserving the union of concrete details from each (e.g. A's `~2^128` wraparound / continued-drain detail, B's missing-input-validation and precondition detail).
- I did **not** promote Report A's *cleared* item (the `uint128(quoteAmount)` downcast, which A explicitly verified is non-exploitable) to a finding, since it is not a vulnerability in either report.

(Note: I attempted to also save this to `/tmp/merged_security_audit.md` but the write wasn't permitted, so the report is inline above. Let me know if you'd like it written to a specific path.)

