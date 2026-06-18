# Audit: 2024-05-loop

Both reports are inline and I have everything needed to merge them — no file access or sub-agents required. Here is the consolidated report.

---

# Merged Security Audit Report — `PrelaunchPoints.sol`

Two independent reviews were reconciled. Reviewer A = Claude, Reviewer B = Codex. Line numbers differ between reviewers (they appear to have numbered slightly different copies of the file); both line references are preserved where they describe the same code.

## Consensus findings

## Token claims credit the whole contract ETH balance, letting a claimer sweep unaccounted ETH
*(consensus)*
- Location: `src/PrelaunchPoints.sol` : `_claim` (token branch, A ≈250–258 / B ≈201–213), with `_fillQuote` (A ≈483–500 / B ≈363–379) and `receive()` (B ≈340)
- Mechanism: After the 0x swap, the token-claim branch sets `claimedAmount = address(this).balance;` and then `lpETH.deposit{value: claimedAmount}(_receiver);` — it credits the **entire contract ETH balance**, not the ETH delta produced by that specific swap. `_fillQuote` already measures that delta as `boughtETHAmount`, but only emits it in an event and discards it. The comment "At this point there should not be any ETH in the contract" is an unenforced assumption. The contract also exposes an unrestricted, `payable` `receive()` that silently accepts ETH (direct sends or force-sent ETH), and there is no `recoverETH` to retrieve it. Any such stray/residual ETH is folded into the first token-claimer's `claimedAmount` and minted to them as lpETH. Additionally, if `_percentage` rounds a dust `userClaim` to zero, the attacker can trigger this sweep without reducing their recorded token stake.
- Impact: A user holding any non-ETH token balance can capture all stray ETH held by the contract once claims begin — including accidental direct sends and force-sent ETH — converting it into lpETH credited to their own `_receiver`. With the dust-rounding case, the sweep can occur without decrementing the attacker's recorded stake. Fix: credit `boughtETHAmount` from `_fillQuote` instead of `address(this).balance`.

## Additional findings (single-reviewer)

## 0x swap-data validation bypass — validated calldata region is not the region 0x decodes (UniswapV3 path)
*(Reviewer A only)*
- Location: `src/PrelaunchPoints.sol` : `_decodeUniswapV3Data` (≈431–451) feeding `_validateData` (≈388–425) and `_fillQuote` (≈483–500)
- Mechanism: `claim` forwards raw `_data` verbatim to the 0x exchange proxy via `payable(exchangeProxy).call{value: 0}(_swapCallData)`. For `sellTokenForEthToUniswapV3(bytes encodedPath, uint256 sellAmount, uint256 minBuyAmount, address recipient)`, `encodedPath` is a **dynamic** parameter whose true location is the ABI offset pointer at calldata offset 4. `_decodeUniswapV3Data` ignores that pointer and hard-codes the path location:
  ```
  encodedPathLength := calldataload(add(p, 96))            // assumes path length at offset 132
  inputToken       := shr(96, calldataload(add(p, 128)))   // assumes first token at offset 164
  outputToken      := shr(96, calldataload(add(p, add(encodedPathLength, 108))))
  ```
  An attacker sets the offset pointer so the path 0x actually decodes lives in one calldata region, while a fabricated path (`inputToken=_token`, `outputToken=WETH`) sits at the fixed offsets `_validateData` inspects. The validator passes on the fake region; 0x executes a different, attacker-chosen route. The fix is to follow the real ABI offset pointer (or use `abi.decode`) rather than fixed offsets.
- Impact: Breaks the core validation invariant that the proxy only performs the exact swap that was checked; the executed route and intermediate hops become unconstrained. Becomes concrete fund loss when combined with the residual-allowance finding (selling a different, still-approved token) and the full-balance-credit consensus finding (crediting the proceeds to the attacker).

## Residual `exchangeProxy` allowance is never reset and minimum output is unvalidated
*(Reviewer A only)*
- Location: `src/PrelaunchPoints.sol` : `_fillQuote` (≈488–498)
- Mechanism: `_fillQuote` sets `require(_sellToken.approve(exchangeProxy, _amount))` and never resets the allowance to zero afterward. `_validateData` checks the sell side (`inputToken`, `outputToken`, `inputTokenAmount`) but never validates `minBuyAmount` / `minOutputTokenAmount`, nor that the swap fully consumes the approval. On a partial fill (or an attacker-crafted route via the UniswapV3 bypass), leftover allowance for that token persists, and the proxy can later be re-invoked with only-selector-validated calldata. Fix: reset allowance to 0 after the swap (or use `forceApprove`) and validate the minimum output / full consumption of `_amount`.
- Impact: Latent cross-user fund-loss path — one user's leftover allowance becomes spendable by a later claim of a different token, with the ETH proceeds redirected through the full-balance credit.

## `recipient == address(0)` accepted in swap validation
*(Reviewer A only)*
- Location: `src/PrelaunchPoints.sol` : `_validateData` (≈418–421)
  ```
  if (recipient != address(this) && recipient != address(0)) {
      revert WrongRecipient(recipient);
  }
  ```
- Mechanism: The check permits a zero-address swap recipient in addition to `address(this)`. For `TransformERC20` `recipient` is never decoded and defaults to `address(0)`, so the allowance is needed there; but for the UniswapV3 branch it also lets a caller pass `recipient = address(0)`. 0x's UniswapV3 feature treats a zero recipient as "send to `msg.sender`" (the contract), so ETH usually still returns to the contract — but this relies on an external-contract convention rather than an explicit guarantee. Fix: require `recipient == address(this)` for the UniswapV3 path.
- Impact: Defense-in-depth weakness — output routing depends on a 0x-side convention rather than an asserted invariant. Any divergence in proxy behavior over `address(0)` recipients translates, via the full-balance credit, into mis-accounted claims.

## Fee-on-transfer / deflationary tokens make recorded balances exceed actual reserves
*(Reviewer B only)*
- Location: `src/PrelaunchPoints.sol` : `_processLock`, `_claim`, `withdraw` (around lines 135–148, 201–213, 238–257)
- Mechanism: Token deposits credit `balances[_receiver][_token] += _amount` after `safeTransferFrom`, without measuring the actual received balance delta. For fee-on-transfer or deflationary tokens, the recorded balance exceeds what the contract actually received. Later `withdraw` and `_claim` operate on the recorded amount rather than the actual reserve share. Precondition: such a token is in the allowed set or later changes its transfer behavior.
- Impact: Early withdrawers/claimers can consume more than their net contribution, leaving later users unable to withdraw or claim their recorded balances (reserve shortfall / insolvency).

---

### Notes (paths reviewed and deemed safe — from Reviewer A)
- `withdraw` follows checks-effects-interactions (balance zeroed and `totalSupply` decremented before the ETH `call`), so the `AttackContract` reentrancy reverts with `CannotWithdrawZero`; cross-function reentrancy into `claim` is likewise blocked.
- ETH-claim math `userStake.mulDiv(totalLpETH, totalSupply)` keeps a fixed ratio (neither value decremented per claim), so claims sum exactly to `totalLpETH`; no share drift or first-depositor inflation.
- `_percentage > 100` underflows `userStake - userClaim` and reverts (caller self-DoS only).
- `uint32` casts of `block.timestamp (+120 days)` do not truncate until ~2106.
- `recoverERC20` correctly blocks `lpETH` and all allowed (lockable) tokens.

