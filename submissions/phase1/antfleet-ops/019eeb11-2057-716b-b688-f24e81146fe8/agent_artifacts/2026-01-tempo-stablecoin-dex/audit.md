# Audit: 2026-01-tempo-stablecoin-dex
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

I merged all 6 reports (3 shots × 2 models). Distinct findings by code-path + root-cause: **6**. Findings emitted below: **6**. No findings dropped. Every distinct claim — including the `withdraw` CEI finding that one report explicitly defended — is preserved.

---

## Consensus findings

## Unauthenticated `emergencyWithdraw` with unchecked underflow drains all liquidity
*(consensus, 6 of 6 reports)*
- Location: `contracts/StablecoinDEX.sol` : `emergencyWithdraw` / `_processWithdrawal`
- Mechanism: `emergencyWithdraw(token, amount)` has no caller restriction and no balance check. It forwards `msg.sender`, `token`, `amount` to `_processWithdrawal`, which does `balances[user][token] -= amount; totalDeposits[token] -= amount;` inside an `unchecked` block, then `safeTransfer(user, amount)`. With insufficient (e.g. zero) recorded balance the subtraction underflows/wraps to ~2^128 instead of reverting, and the transfer still executes. The normal-path guard (`if (balances[...] < amount) revert`) that protects `withdraw` is entirely absent here.
- Impact: Any address, having deposited nothing, can call `emergencyWithdraw(token, contractBalance)` and drain the contract's entire holding of any token in a single permissionless transaction (ceiling is only the contract's real balance, above which `safeTransfer` reverts). Several reports add that the wrapped phantom `balances` value also lets the attacker keep extracting/placing orders against the bogus balance and corrupts `totalDeposits`. Critical / total loss of funds.
- Reviewer disagreement (if any): none — all reports concur this is the dominant, deploy-blocking bug.

## `cancel` is missing maker authorization — anyone can cancel anyone's order
*(consensus, 6 of 6 reports)*
- Location: `contracts/StablecoinDEX.sol` : `cancel` / `_cancelOrder`
- Mechanism: `cancel(orderId)` only checks order existence (`order.maker == address(0)` ⇒ revert) and never verifies `msg.sender == order.maker` before calling `_cancelOrder`, which unlinks the order and refunds `order.remaining` to `balances[maker][baseToken]`. Two reports note the unused `Unauthorized` error (and unused `UserBalance` struct) suggest the check was intended and dropped.
- Impact: An attacker cannot redirect funds (the refund credits the rightful maker), but can force-cancel every resting order in the book at will — a permissionless griefing / liquidity-denial / order-book-manipulation primitive: wipe competing liquidity, force makers' positions closed during volatility, disrupt routing, and force missed fills. Medium–High integrity break.
- Reviewer disagreement (if any): none.

## `fillOrder` rounds the quote payment down in the taker's favor (maker underpaid)
*(consensus, 6 of 6 reports)*
- Location: `contracts/StablecoinDEX.sol` : `fillOrder`
- Mechanism: `quoteAmount = (uint256(amount) * uint256(order.price)) / 1e18` floors the division, and that floored value is what the taker pays and the maker receives; the only guard is `quoteAmount != 0`. There is no minimum on the per-fill `amount` (`MIN_ORDER_SIZE` is enforced only in `placeOrder`, never on the fill), so a taker can split a fill into many tiny pieces, each paying `floor(amount*price/1e18)` and discarding the fractional quote remainder in the taker's favor while still receiving full base `amount`.
- Impact: A taker systematically underpays the maker relative to the posted price. Most reports bound the leak to <1 quote base-unit (~1e-6) per fill and call it gas-limited / economically marginal; however gpt-5.5 shots illustrate it can be material at non-parity prices (e.g. at `price = 1.01e18`, filling one base-unit at a time pays `1` instead of `1.01` — ~1% extraction; at `price = 0.99e18`, `amount = 2` chunks pay `1` instead of `1.98`). Value transferred maker→taker, compounding across partial fills. Low–Medium.
- Reviewer disagreement (if any): none on direction; reports differ only on magnitude (sub-unit dust vs. up to ~1%+ at arbitrary prices).

## `deposit` credits the requested amount, not the amount actually received (fee-on-transfer / short-transfer overcredit)
*(consensus, 3 of 6 reports)*
- Location: `contracts/StablecoinDEX.sol` : `deposit`
- Mechanism: `deposit` does `balances[msg.sender][token] += amount; totalDeposits[token] += amount;` after `safeTransferFrom`, but never measures the contract's actual token-balance delta. Fee-on-transfer, burn-on-transfer, rebasing, or policy-modified TIP-20/ERC20 tokens can deliver less than `amount` while the DEX records the full `amount`.
- Impact: For any such token with honest liquidity, internal accounting exceeds real assets — the depositor receives more credit than was received, making the token pool insolvent. An attacker can later withdraw/trade against the inflated balance, consuming other users' same-token liquidity or breaking later withdrawals.
- Reviewer disagreement (if any): the three opus shots examined `deposit` and called it sound against reentrancy/double-credit (`deposit` orders state correctly, transfer-then-credit) — but addressed only that root cause and did not consider short-transfer/fee-on-transfer tokens, so this is not a direct defense of the same root cause.

## `MAX_PRICE_DEVIATION` price-band invariant is declared but never enforced
*(consensus, 3 of 6 reports)*
- Location: `contracts/StablecoinDEX.sol` : `placeOrder` (price validation)
- Mechanism: The contract declares `MAX_PRICE_DEVIATION = 1e16` ("1% from parity") as a stated safety bound for stablecoin pairs, but `placeOrder` only rejects `price == 0` — any arbitrary price is accepted, so orders can rest arbitrarily far from parity. (Distinct code path and root cause from the `fillOrder` rounding bug above: unenforced placeOrder invariant vs. round-down division.)
- Impact: The advertised stablecoin price band is silently ignored. The automated routing layer (`getOrders` feeds the documented LCA routing algorithm) may assume near-parity execution and can be steered into bad fills; it also unbounds the per-fill rounding leakage. opus shot 2 flags this as the *substantive* issue of the pair.
- Reviewer disagreement (if any): none explicit; the three reports that omit it simply did not surface it as a separate finding.

## `withdraw` performs the external token transfer before updating state (CEI violation / reentrancy)
*(consensus, 2 of 6 reports)*
- Location: `contracts/StablecoinDEX.sol` : `withdraw`
- Mechanism: After checking `balances[msg.sender][token] < amount`, the function calls `IERC20(token).safeTransfer(msg.sender, amount)` **before** decrementing `balances`/`totalDeposits`. The contract is explicitly designed for TIP-20 tokens with TIP-403 compliance/transfer-policy and memo hooks, i.e. tokens that hand control to a callback during transfer; from that callback the attacker re-enters `withdraw` (or `placeOrder`/`fillOrder`) while the balance is still un-decremented, so the `< amount` check still passes and a second transfer fires. No `nonReentrant` guard exists anywhere in the contract.
- Impact: opus shot 3 rates it High — an attacker depositing X recursively withdraws multiples of X (or locks the same balance into orders), draining other users' funds, conditional on the deployed token honoring a transfer hook (exactly the compliance feature this DEX advertises). opus shot 2 rates it a latent defect that becomes a live drain under any future function that credits `balances` without matching inflow, or unexpected hook semantics.
- Reviewer disagreement (if any): opus shot 1 examined this exact code path and defended it as non-exploitable — the decrement uses *checked* arithmetic, so any nested over-withdrawal makes a later `-=` underflow and revert, unwinding the whole call; it could not construct a value-extracting path (still recommends `nonReentrant` + reordering).

---

## Minority findings

None. Every distinct finding (by code path + root cause) surfaced in two or more reports, so all six appear under Consensus above. The closest thing to a sole-reviewer/conflict case — the `withdraw` CEI/reentrancy finding — was raised by two reports and explicitly defended by a third; it is retained in Consensus with that disagreement recorded inline rather than dropped.

*(Examined-and-dismissed items that no report raised as a finding — and are therefore not findings: the `uint128(quoteAmount)` downcast in `fillOrder`, dismissed by three reports because the preceding `balances[...] < quoteAmount` comparison is done in full `uint256` against a `uint128` balance, so any `quoteAmount ≥ 2^128` reverts before the cast and taker-debit/maker-credit/event all use the same value; and `MockTIP20.mint`, which all reports agree is `minter`-gated and sound. Listed only for completeness; not counted as findings.)*

