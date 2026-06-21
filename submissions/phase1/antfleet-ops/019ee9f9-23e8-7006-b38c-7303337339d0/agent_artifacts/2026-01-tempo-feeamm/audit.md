# Audit: 2026-01-tempo-feeamm

# FeeAMM Security Audit Report

Analysis is based on the provided `FeeAMM.sol` contract. Findings below are limited to genuine security issues (logic, access control, reentrancy, accounting, token compatibility).

---

## Unchecked ERC20 Return Values Allow Reserve Theft

- **Location:** `FeeAMM.sol` : `executeFeeSwap`, `rebalanceSwap`, `mint`, `burn`
- **Mechanism:** All token movements use bare `IERC20.transfer` / `transferFrom` and never check the returned `bool`. Tokens such as USDT (and many bridged stables) return `false` on failure instead of reverting. In `executeFeeSwap`, `transferFrom` is called first; even if it returns `false` and no `userToken` is received, the next lines still credit `pool.reserveUserToken` and debit `pool.reserveValidatorToken`, then call `transfer` of `validatorToken` to `msg.sender`. In `rebalanceSwap`, reserves are updated **before** `transferFrom`; if `transferFrom` silently fails, `userToken` is still sent to `to` while `reserveUserToken` is reduced and `reserveValidatorToken` is increased without payment.
- **Impact:** An attacker can withdraw `validatorToken` / `userToken` from pool reserves without depositing the paired asset, draining LP funds and desynchronizing reserves from real balances.

```solidity
IERC20(userToken).transferFrom(msg.sender, address(this), amountIn);
pool.reserveUserToken += uint128(amountIn);           // runs even if transferFrom returned false
pool.reserveValidatorToken -= uint128(amountOut);
IERC20(validatorToken).transfer(msg.sender, amountOut);
```

---

## Reentrancy in `burn` (Checks-Effects-Interactions Violation)

- **Location:** `FeeAMM.sol` : `burn`
- **Mechanism:** `burn` performs external token transfers to `to` before updating `liquidityBalances`, `totalSupply`, or pool reserves. If `userToken` or `validatorToken` implements transfer hooks (ERC777-style, ERC1363, or a custom TIP-20 with callbacks), the recipient contract can reenter `burn` during `transfer` while the caller’s LP balance is still fully credited.
- **Impact:** A malicious `to` contract can burn the same LP shares multiple times in one transaction, withdrawing more `userToken` and `validatorToken` than its liquidity entitles, draining the pool and other LPs.

```solidity
IERC20(userToken).transfer(to, amountUserToken);
IERC20(validatorToken).transfer(to, amountValidatorToken);
// state updates only after external calls
liquidityBalances[poolId][msg.sender] -= liquidity;
totalSupply[poolId] -= liquidity;
pool.reserveUserToken -= uint128(amountUserToken);
pool.reserveValidatorToken -= uint128(amountValidatorToken);
```

---

## Reentrancy in `executeFeeSwap` via `transferFrom`

- **Location:** `FeeAMM.sol` : `executeFeeSwap`
- **Mechanism:** `transferFrom` on `userToken` happens before reserve updates. If `userToken` invokes a hook on the payer or receiver during `transferFrom`, a reentrant call can execute another `executeFeeSwap` against the same stale reserves before the outer call updates state. Both calls can pass the `reserveValidatorToken >= amountOut` check and each transfer out `validatorToken`.
- **Impact:** With a hookable `userToken` and sufficient allowance, an attacker can double-spend liquidity checks and withdraw `validatorToken` multiple times per single legitimate `userToken` deposit, draining the pool.

---

## `rebalanceSwap` Updates Reserves Before Receiving Tokens

- **Location:** `FeeAMM.sol` : `rebalanceSwap`
- **Mechanism:** The function increments `reserveValidatorToken` and decrements `reserveUserToken` before `transferFrom` pulls `validatorToken`. Combined with unchecked return values (finding 1), a failed or partial `transferFrom` still leaves reserves reflecting full payment. Even with reverting tokens, this ordering violates CEI and enables reentrancy after reserves are mutated but before tokens are received.
- **Impact:** Reserve accounting can credit paid-in `validatorToken` that was never received; reentrancy during the subsequent `userToken.transfer(to, ...)` can exploit stale or incorrect reserve state to extract extra `userToken` or compose with other entrypoints.

```solidity
pool.reserveValidatorToken += uint128(amountIn);
pool.reserveUserToken -= uint128(amountOut);
IERC20(validatorToken).transferFrom(msg.sender, address(this), amountIn);
IERC20(userToken).transfer(to, amountOut);
```

---

## Fee-on-Transfer / Deflationary Token Accounting Mismatch

- **Location:** `FeeAMM.sol` : `executeFeeSwap`, `rebalanceSwap`, `mint`
- **Mechanism:** Reserves are incremented by the nominal `amountIn` / `amountValidatorToken` argument, not by measuring `balanceAfter - balanceBefore`. If a token charges a fee on transfer, the contract receives less than the amount credited to reserves.
- **Impact:** `reserve*` values exceed actual token balances. Later `burn` or swap withdrawals revert or leave the last LPs unable to redeem full reserves (insolvency). An attacker can also donate via fee mechanics to create a griefing/DoS state where accounting promises more tokens than the contract holds.

---

## No Decimal Normalization Between Token Pairs

- **Location:** `FeeAMM.sol` : `executeFeeSwap`, `rebalanceSwap`, `mint`, `burn`, `_calculateBurnAmounts`
- **Mechanism:** All pricing uses raw token amounts with fixed ratios `M/SCALE` and `N/SCALE`. There is no `decimals()` normalization. A pool between a 6-decimal stable and an 18-decimal stable treats `1` base unit of each as equal.
- **Impact:** Swaps and LP mint/burn math are wrong by orders of magnitude. An attacker can trade the mispriced side to extract value from LPs (e.g., deposit cheap units of the high-decimal token path and withdraw valuable low-decimal units, or vice versa).

---

## Permissionless Pools Allow Worthless-Token Drain of LP `validatorToken`

- **Location:** `FeeAMM.sol` : `mint`, `executeFeeSwap`
- **Mechanism:** There is no allowlist or factory-only pool creation. Anyone can call `mint` for any `(userToken, validatorToken)` pair. `executeFeeSwap` prices solely at the fixed `M/SCALE` rate and does not validate `userToken` economic value. An attacker can create a pool with a worthless self-minted `userToken`, convince or wait for LPs to deposit real `validatorToken`, then swap unlimited worthless `userToken` for `validatorToken` at ~0.997:1 raw units.
- **Impact:** LPs who deposited `validatorToken` into a pool whose `userToken` is not the intended fee asset lose their `validatorToken` to the attacker. This is especially dangerous if UI/docs assume canonical TIP-20 addresses but the contract accepts any address.

---

## Unchecked Arithmetic Underflow/Overflow (Solidity 0.7.6)

- **Location:** `FeeAMM.sol` : all functions updating `Pool` reserves, `totalSupply`, `liquidityBalances`
- **Mechanism:** The contract uses `pragma solidity >=0.7.6 <0.8.0` without `SafeMath`. In 0.7.x, arithmetic wraps on overflow/underflow instead of reverting. Reserve fields are `uint128` and are updated via `+=` / `-=`; `totalSupply` and `liquidityBalances` are `uint256` with unchecked addition/subtraction.
- **Impact:** In extreme (or crafted) states, wrapped `totalSupply` or reserves can cause `_calculateBurnAmounts` to compute wildly incorrect withdrawal amounts—potentially near-draining reserves—or silently corrupt pool state. `_requireU128` only bounds individual operands, not sums.

---

## Fixed-Rate Swaps Ignore Pool Composition (LP Arbitrage / Value Extraction)

- **Location:** `FeeAMM.sol` : `executeFeeSwap`, `rebalanceSwap`
- **Mechanism:** Swap outputs depend only on the input amount and constants `M`/`N`, not on the reserve ratio. Unlike a constant-product AMM, imbalanced pools do not adjust price. `rebalanceSwap` pays ~`0.9985 × amountOut + 1` `validatorToken` for `amountOut` `userToken` (in raw units), which is favorable to the swapper when both assets are intended to be 1:1 USD stables.
- **Impact:** External arbitrageurs can systematically trade against imbalanced pools until one reserve is depleted, extracting value from LPs who only deposited `validatorToken` but share pro-rata in both reserves on `burn`. This is economically equivalent to LP loss from mispriced liquidity when the pool deviates from peg or fair 1:1 inventory.

---

## `burn` Can Succeed While Outbound `transfer` Fails Silently

- **Location:** `FeeAMM.sol` : `burn`
- **Mechanism:** Outbound `transfer` return values are ignored. If the first `userToken.transfer` succeeds but `validatorToken.transfer` returns `false`, the function still decrements LP balances and reserves.
- **Impact:** LP shares are destroyed and reserves reduced even though the user did not receive the full owed amounts—loss of funds for the burner. A griefer can also create reserve/accounting states that strand tokens or break expected redemption behavior for remaining LPs.

---

### Summary Table

| Severity (typical) | Finding |
|---|---|
| Critical | Unchecked ERC20 return values |
| High | `burn` reentrancy; `executeFeeSwap` reentrancy; fee-on-transfer accounting |
| High/Medium | No decimal normalization; permissionless worthless-token pools |
| Medium | `rebalanceSwap` CEI ordering; 0.7.6 overflow; fixed-rate LP arbitrage |
| Medium/Low | Silent outbound transfer failure on `burn` |

---

### Notes on Non-Findings

- **Missing swap slippage/deadline parameters** are MEV/UX concerns, not standalone contract bugs given fixed-rate swaps.
- **`MIN_LIQUIDITY` locked supply** permanently locks a small reserve slice (Uniswap-style); this is a known design tradeoff, not an exploitable theft vector.
- **No LP transfer function** is intentional (non-transferable LP balances), not a vulnerability.

If you want, I can switch to Agent mode and propose concrete patches (SafeERC20, CEI reordering, balance-delta accounting, and an allowlisted factory pattern).

