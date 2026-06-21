# Audit: 2024-05-loop

This audit covers `PrelaunchPoints.sol` and its interfaces as provided. The contract is a prelaunch staking/points system: users lock ETH or allowed LRT tokens, the owner converts pooled ETH to `lpETH` after activation, and users later claim `lpETH` (directly or via swap + deposit for non-ETH tokens).

---

## TransformERC20 swap recipient not validated (critical)

- **Location:** `PrelaunchPoints.sol` : `_validateData` / `_decodeTransformERC20Data` / `_claim`
- **Mechanism:** For `Exchange.UniswapV3`, `_decodeUniswapV3Data` returns `recipient` and `_validateData` checks it. For `Exchange.TransformERC20`, `_decodeTransformERC20Data` never reads a recipient, so `recipient` stays the default `address(0)`. The check `if (recipient != address(this) && recipient != address(0))` therefore always passes on the Transform path. Worse, only the first three ABI words (input token, output token, amount) are validated; fields like `minOutputTokenAmount` and especially the `transformations` payload are never inspected before `_fillQuote` forwards raw `_data` to `exchangeProxy`.
- **Impact:** A user (or attacker with any allowed-token balance) can call `claim()` / `claimAndStake()` with crafted 0x `TransformERC20` calldata that passes token/amount checks but routes swap proceeds to an arbitrary address. The contract still debits their stake and approves tokens for the proxy; swapped ETH can be sent to the attacker instead of the contract. The victim receives little or no `lpETH` while swap value is stolen. This matches the core flaw exploited in the April 2024 Loop incident.

---

## Token claims credit full contract ETH balance, not swap output (critical)

- **Location:** `PrelaunchPoints.sol` : `_claim` / `_fillQuote`
- **Mechanism:** `_fillQuote` correctly computes `boughtETHAmount = address(this).balance - boughtETHAmount` but never returns or uses it. `_claim` instead sets `claimedAmount = address(this).balance` and deposits that entire balance into `lpETH`. Any ETH sitting in the contract at that moment is treated as belonging to the current claimer.
- **Impact:**  
  1. Combined with the TransformERC20 flaw above: after a malicious swap sends ETH elsewhere, the claimer may get `claimedAmount ≈ 0` while still losing tokens — but if any unrelated ETH remains in the contract, the claimer absorbs it.  
  2. **Donation theft:** ETH sent via `receive()` (or left as dust) is captured by the first post-conversion token claimer, who receives that extra `lpETH` despite not contributing it.  
  3. **Cross-user value leakage:** If ETH and token operations overlap in state (e.g., timing edge cases before/around conversion), one claimer can mint `lpETH` against ETH that is not the output of their swap.

---

## Uniswap V3 path accepts `recipient = address(0)` (high)

- **Location:** `PrelaunchPoints.sol` : `_validateData`
- **Mechanism:** Recipient validation explicitly allows both `address(this)` and `address(0)`:

```solidity
if (recipient != address(this) && recipient != address(0)) {
    revert WrongRecipient(recipient);
}
```

  For Uniswap V3, `address(0)` is treated as valid even though native ETH must be delivered to the contract for the subsequent `lpETH.deposit{value: claimedAmount}` step.
- **Impact:** Swap calldata with `recipient = address(0)` passes validation. Depending on 0x/Uniswap feature behavior, ETH may be sent to the zero address or otherwise not retained by the contract. The claimer loses swap proceeds (tokens sold, little/no `lpETH` received). An attacker can also grief claimers by supplying malformed quotes that pass this weak recipient check.

---

## No slippage / minimum output enforcement on swaps (high)

- **Location:** `PrelaunchPoints.sol` : `_validateData` / `_decodeUniswapV3Data` / `_decodeTransformERC20Data`
- **Mechanism:** Validation checks input token, output token, input amount, and (partially) recipient. It never reads or enforces `minBuyAmount` (Uniswap V3) or `minOutputTokenAmount` (TransformERC20), which are present in the calldata layout but ignored.
- **Impact:** Claim transactions are fully sandwichable/MEV-extractable. A searcher can manipulate the pool around a victim’s `claim()` so the contract receives far less ETH than fair value; because `_claim` uses `address(this).balance` (not an expected minimum), the victim receives proportionally less `lpETH` with no on-chain revert. This is extractable value from users at claim time.

---

## Fragile manual calldata decoding can desync validation from execution (high)

- **Location:** `PrelaunchPoints.sol` : `_decodeUniswapV3Data` / `_decodeTransformERC20Data` / `_validateData`
- **Mechanism:** Swap safety relies on inline assembly parsing of `_data` rather than decoding the exact ABI layout the 0x proxy will execute. For Uniswap V3, `encodedPathLength` is read from calldata without bounds checks against `_data.length`; out-of-range `calldataload` can yield attacker-controlled words. For TransformERC20, only the first three arguments are parsed while the executed call includes additional dynamic data (`transformations`).
- **Impact:** An attacker can craft calldata where the assembly decoder sees benign values (correct selector, token, amount, WETH/ETH output) while the executed swap behaves differently — different path, different sell behavior, or different fund routing. Validation becomes cosmetic and can be bypassed without matching the actual external call.

---

## Emergency mode does not rescue ETH stakers after claims open (medium)

- **Location:** `PrelaunchPoints.sol` : `withdraw`
- **Mechanism:** `emergencyMode` bypasses the outer time gates on `withdraw`, but the ETH branch still hard-reverts once claiming starts:

```solidity
if (_token == ETH) {
    if (block.timestamp >= startClaimDate){
        revert UseClaimInstead();
    }
```

  Token (LRT) withdrawals remain possible in emergency mode even after `startClaimDate`.
- **Impact:** If swap infrastructure fails, oracles misbehave, or the 0x validation issues above make claiming unsafe, LRT depositors can exit via `withdraw()` in emergency mode, but ETH depositors cannot. ETH stakes are forced through the broken `claim()` path and can become unrecoverable in a realistic failure scenario.

---

## Direct ETH transfers are permanently lost (medium)

- **Location:** `PrelaunchPoints.sol` : `receive`
- **Mechanism:** The contract accepts plain ETH via `receive()`, but `receive()` does not increment `balances`, `totalSupply`, or any accounting. There is no admin recovery path for native ETH (`recoverERC20` only handles ERC20s and explicitly excludes allowed tokens/`lpETH`).
- **Impact:** Any user or contract that sends ETH directly (wrong function, mistaken transfer, forced transfer via `selfdestruct`) loses those funds permanently. Separately, ETH sent this way can be captured by a token claimer via the “full balance” bug above, creating an unintended redistribution rather than recovery.

---

## Rebasing / fee-on-transfer tokens break accounting if allowed (medium)

- **Location:** `PrelaunchPoints.sol` : `allowToken` / `_processLock` / `_claim` / `withdraw`
- **Mechanism:** `allowToken` can whitelist arbitrary ERC20s. Internal accounting uses the requested `_amount` in `balances`, but `_processLock` uses `safeTransferFrom` without measuring received balance. Comments warn about rebase tokens, but nothing enforces wrapped/non-rebase assets.
- **Impact:** For fee-on-transfer tokens, the contract receives less than recorded; later claimers/withdrawers can drain other users’ deposits. For rebasing tokens, `balances` diverges from actual holdings, enabling over-withdrawal or causing insolvency when the last users exit.

---

## Summary of exploitable paths

| Severity | Issue | Primary attack path |
|----------|-------|---------------------|
| Critical | TransformERC20 incomplete validation | `claim(token, pct, TransformERC20, maliciousData)` → ETH routed to attacker |
| Critical | Full-balance `lpETH` deposit | Same path + donation/timing leakage |
| High | `recipient == 0` allowed (Uniswap) | Malformed/malicious Uniswap quotes pass validation |
| High | No min-output checks | MEV sandwich on `claim()` |
| High | Assembly decode vs execution mismatch | Validation bypass on swap calldata |
| Medium | Emergency ETH lock-in | ETH users stuck if claim path fails |
| Medium | `receive()` ETH unaccounted | Permanent loss / unintended capture |
| Medium | Non-standard ERC20 allowed | Insolvency / over-withdrawal |

The two critical findings (unvalidated TransformERC20 routing + `address(this).balance` accounting) are the ones that make this contract unsafe for production use and align with the known Loop PrelaunchPoints exploit class. If you want, I can walk through a concrete end-to-end attack transaction sequence for the TransformERC20 path in Agent mode.

