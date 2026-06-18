# Audit: 2026-01-tempo-feeamm

I have both reports in full and they're self-contained, so I can merge them directly without re-auditing. Let me map the findings.

**Overlap analysis:**
- A's "Reentrancy in `burn`" ≡ B's "Burn performs external transfers before accounting updates" → same root cause, same code path → **consensus**
- A's "ERC-20 return values are never checked" ≡ B's "ERC-20 transfers are not checked" → same → **consensus**
- A's remaining four findings (`executeFeeSwap` reentrancy, `mint` valuation discount, unchecked reserve overflow, fee-on-transfer) have no B counterpart → **A only**
- B has no findings beyond the two consensus ones.

Here is the merged report.

---

# Merged Security Audit — `contracts/FeeAMM.sol`

Context shared by both reviewers: the pragma is `>=0.7.6 <0.8.0`, so **all arithmetic is unchecked** (silent wrap on over/underflow), and the contract accepts **arbitrary, caller-chosen token addresses** (no whitelist), placing ERC-777-style/hooked/malicious tokens in scope. These two facts are what escalate the CEI violations below into drains.

## Consensus findings

## Reentrancy in `burn`: same LP shares redeemed repeatedly (pool drain)
*(consensus — Reviewer A & B)*
- Location: `contracts/FeeAMM.sol` : `burn` (approx. lines 245–295)
- Mechanism: `burn` performs both external token transfers **before** updating any state, violating checks-effects-interactions:
  ```
  IERC20(userToken).transfer(to, amountUserToken);
  IERC20(validatorToken).transfer(to, amountValidatorToken);
  liquidityBalances[poolId][msg.sender] -= liquidity;   // state updated AFTER transfers
  totalSupply[poolId] -= liquidity;
  pool.reserveUserToken -= uint128(amountUserToken);
  pool.reserveValidatorToken -= uint128(amountValidatorToken);
  ```
  The guard `liquidityBalances[poolId][msg.sender] < liquidity` is checked, but the balance is only decremented after the transfers. There is no reentrancy guard, and either pool token may be a malicious/hooked ERC-20 chosen by the caller (ERC-777 `tokensReceived` on `to`, or an attacker-authored token). On re-entry during the first `transfer`, `liquidityBalances[msg.sender]` is still the original value and the reserves are still un-decremented, so `_calculateBurnAmounts` returns the same proportional amounts again. This recurses, paying out the pool many times for one LP position. As the stack unwinds, the trailing `-=` operations underflow `uint128`/`uint256` (no revert in 0.7), corrupting `totalSupply`/reserves.
- Impact: An attacker who holds liquidity in a pool where at least one token is malicious/reentrant calls `burn` with `to` = an attacker contract, redeeming the same `liquidity` repeatedly and draining the pool's real `userToken` and `validatorToken` balances (including the paired asset). Because tokens are paid from `address(this)`'s shared balance, other pools sharing that token are also at risk. No flash loan required — the most severe issue in the contract.

## ERC-20 transfer/transferFrom return values are never checked
*(consensus — Reviewer A & B)*
- Location: `contracts/FeeAMM.sol` : every `IERC20(...).transfer(...)` / `transferFrom(...)` call in `executeFeeSwap`, `rebalanceSwap`, `mint`, `burn`
- Mechanism: All transfers ignore the returned `bool` and no `SafeERC20` wrapper is used. Tokens that return `false` on failure instead of reverting (documented behavior for several widely-used stablecoins) appear to succeed, and the contract proceeds to update reserves and `liquidityBalances` as though tokens moved. This affects inbound transfers in `executeFeeSwap`, `rebalanceSwap`, and `mint`, and outbound transfers in `burn`.
- Impact: A non-reverting failed `transferFrom` in `executeFeeSwap`/`mint` credits reserves/shares without the contract receiving tokens (free shares / free reserve inflation — e.g. `executeFeeSwap` credits `reserveUserToken` and sends `validatorToken` even when `userToken.transferFrom` failed); a non-reverting failed `transfer` in `burn` burns the LP's shares while sending nothing. Precondition: an affected pool uses an ERC-20 with false-returning transfer semantics. Fix: require success / use `SafeERC20`.

## Additional findings (single-reviewer)

## Reentrancy / CEI violation in `executeFeeSwap` drains validator-token reserves
*(Reviewer A only)*
- Location: `contracts/FeeAMM.sol` : `executeFeeSwap` (approx. lines 99–134)
- Mechanism: The reserve check happens, then the inbound `transferFrom` is called **before** reserves are updated:
  ```
  require(pool.reserveValidatorToken >= amountOut, "INSUFFICIENT_LIQUIDITY");
  IERC20(userToken).transferFrom(msg.sender, address(this), amountIn); // external call first
  pool.reserveUserToken += uint128(amountIn);
  pool.reserveValidatorToken -= uint128(amountOut);                    // effect after call
  IERC20(validatorToken).transfer(msg.sender, amountOut);
  ```
  If `userToken` is an ERC-777/hooked/malicious token, its `transferFrom` invokes a `tokensToSend` hook on the attacker, who re-enters `executeFeeSwap` while `reserveValidatorToken` is still the stale, un-decremented value. The check `reserveValidatorToken >= amountOut` passes again, paying out more `validatorToken` than the pool holds. When the outer call finally runs `pool.reserveValidatorToken -= uint128(amountOut)`, the subtraction underflows `uint128` (silent wrap in 0.7) to ~`2^128`, after which the attacker can keep draining `validatorToken` across every pool sharing that token's balance.
- Impact: Drain of validator-token reserves and permanent corruption of `reserveValidatorToken`. Note `rebalanceSwap` updates state *before* its external calls (correct CEI) — this asymmetry confirms `executeFeeSwap` (and `burn`) got the ordering wrong.

## Single-sided `mint` undervalues the userToken reserve (mint→burn value extraction)
*(Reviewer A only)*
- Location: `contracts/FeeAMM.sol` : `mint` (subsequent-deposit branch, approx. lines 215–221) vs `_calculateBurnAmounts` (approx. lines 297–314)
- Mechanism: `mint` only accepts `validatorToken` and prices new shares against
  ```
  product = (N * reserveUserToken) / SCALE;        // 0.9985 * U
  denom   = reserveValidatorToken + product;        // V + 0.9985*U
  liquidity = (amountValidatorToken * _totalSupply) / denom;
  ```
  i.e. it values the existing `userToken` reserve at a 0.15% discount (`N/SCALE = 0.9985`). But `burn` returns `userToken` at full value: `amountUserToken = liquidity * reserveUserToken / totalSupply`. Since `denom = V + 0.9985·U` is strictly smaller than the par pool value `V + U` whenever `U > 0`, a depositor receives *more* shares than the value contributed. A deposit of `d` followed immediately by burning the minted shares returns `d·(V+U+d)/(V+0.9985U+d) > d` — net profit `≈ d·0.0015·U/(V+0.9985U+d)`, approaching `0.0015·U` for large `d` (flash-loan-fundable since both legs are ~$1 stablecoins).
- Impact: Any actor can mint then immediately burn to skim up to ~0.15% of the pool's accumulated `userToken` reserve per cycle, paid by existing LPs (dilution). A correct implementation must value the existing reserve at par or higher (`denom ≥ V + U`). A repeatable drain of LP value, not just a rounding artifact.

## Unchecked reserve overflow in `executeFeeSwap` and `mint` (Solidity 0.7 wrap)
*(Reviewer A only)*
- Location: `contracts/FeeAMM.sol` : `executeFeeSwap` (`pool.reserveUserToken += uint128(amountIn)`, ~line 124) and `mint` (`pool.reserveValidatorToken += uint128(amountValidatorToken)`, ~line 233)
- Mechanism: `_requireU128` bounds each individual `amountIn`/`amountValidatorToken` to `≤ uint128.max` but does **not** check the running sum. Under 0.7 the `uint128 += uint128` additions have no overflow guard, so a reserve plus the new amount exceeding `uint128.max` wraps to a small value. `rebalanceSwap` explicitly guards this (`if (reserveValidatorToken + amountIn > type(uint128).max) revert`); the other two accumulation paths do not — an inconsistency signaling the omission is a bug.
- Impact: A wrapped reserve under-counts assets, so subsequent `burn`/swap math computes wrong (tiny) payouts and accounting is corrupted. Reaching `uint128.max` (≈3.4e38 base units) is impractical for high-decimal tokens, so severity is low in isolation, but it is a real missing check that removes a bound the contract enforces elsewhere.

## Fee-on-transfer / rebasing tokens break reserve accounting
*(Reviewer A only)*
- Location: `contracts/FeeAMM.sol` : `executeFeeSwap` (`pool.reserveUserToken += uint128(amountIn)`) and `mint` (`pool.reserveValidatorToken += uint128(amountValidatorToken)`)
- Mechanism: The code credits the *requested* amount to reserves, not the amount actually received. For a fee-on-transfer token, `transferFrom(...amount...)` delivers `amount - fee`, but reserves are increased by the full `amount`, so reserves exceed real balances.
- Impact: Reserves drift above the contract's true token balance; later `burn`/swap payouts computed from inflated reserves will revert or, worse, succeed by paying out from balances belonging to other pools sharing that token. Conditional on any supported "TIP-20 stablecoin" charging transfer fees — tied to the token set rather than a guaranteed exploit.

---

**Note on access control (not a standalone finding):** `mint`, `burn`, `executeFeeSwap`, and `rebalanceSwap` are all unrestricted. For swap/LP entry points that is normal AMM design, but combined with arbitrary-token-address acceptance it is what makes the reentrancy findings directly exploitable — there is no whitelist gating which `transfer`/`transferFrom` callbacks can fire. Both reviewers agree the two reentrancy issues (`burn`, plus A's `executeFeeSwap`) are critical and should be fixed by moving all state updates before external calls and adding a `nonReentrant` guard.

