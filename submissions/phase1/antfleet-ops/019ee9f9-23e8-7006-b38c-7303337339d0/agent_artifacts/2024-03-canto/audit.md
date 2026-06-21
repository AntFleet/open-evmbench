# Audit: 2024-03-canto

# Security Audit Report

Findings below are limited to genuine security vulnerabilities in the provided contracts. Thin wrappers (`OFT.sol`, `OFTAdapter.sol`) and test mocks are omitted unless they affect production paths.

---

## Unauthenticated `lzCompose` enables theft of bridged funds

- **Location:** `contracts/asd/asdRouter.sol` : `lzCompose`
- **Mechanism:** `lzCompose` is `external payable` with no validation that `msg.sender` is the LayerZero endpoint, executor, or any authorized party. The function fully trusts caller-supplied `_message` bytes: `amountLD`, `composeFrom`, and `composeMsg` are decoded via `OFTComposeMsgCodec` without being checked against an on-chain LayerZero compose payload. In the OFT compose flow, bridged OFT tokens are delivered to the router in `lzReceive` and compose runs in a separate step, so tokens can sit on the router before compose executes. Any address may call `lzCompose` first and supply arbitrary message data.
- **Impact:** An attacker can frontrun or preempt the legitimate executor and steal bridged USDC-OFT (or any whitelisted OFT) sitting on the router. Two concrete paths:
  1. **Invalid-length refund path** — craft `_message` with `amountLD` equal to the router’s token balance and `composeMsg.length != 224`; the contract refunds `amountLD` of `_from` to `composeFrom`, which the attacker sets to their address (lines checking length occur before whitelist/deposit).
  2. **Full payload path** — craft a valid 224-byte `OftComposeMessage` with `_dstReceiver` / `_cantoRefundAddress` controlled by the attacker, routing swapped NOTE/ASD to the attacker.

This is the highest-severity issue in the codebase.

---

## Arbitrary ASD vault address allows NOTE theft on hijacked compose

- **Location:** `contracts/asd/asdRouter.sol` : `lzCompose` → `_depositNoteToASDVault`
- **Mechanism:** `payload._cantoAsdAddress` is user-/attacker-supplied and never validated to be a legitimate `ASDOFT` deployment. `_depositNoteToASDVault` approves that address for `_amountNote` NOTE and calls `mint(uint256)` via low-level `call`. A malicious contract can implement `mint` to pull approved NOTE via `transferFrom` and optionally mint worthless ERC-20 “ASD” back to the router so the subsequent `transfer` in `_sendASD` does not revert.
- **Impact:** Combined with unauthenticated `lzCompose`, after the USDC→NOTE swap the attacker’s vault can steal all NOTE held by the router. The victim loses bridged value even if the final ASD transfer appears to succeed with a worthless token.

---

## Unsafe `IERC20.transfer` in refund path can silently fail

- **Location:** `contracts/asd/asdRouter.sol` : `_refundToken`
- **Mechanism:** Refunds use `IERC20(_tokenAddress).transfer(_refundAddress, _amount)` instead of `SafeERC20.safeTransfer`. Tokens that return `false` on failure (e.g. some USDC implementations) do not revert; execution continues after `TokenRefund` is emitted.
- **Impact:** A failed refund is recorded as successful while tokens remain on the router. Those stranded tokens can then be taken by anyone exploiting unauthenticated `lzCompose`. Users who should receive refunds on failed swap/deposit/send paths can lose funds.

---

## `uint128` truncation can desync swap amount from deposited balance

- **Location:** `contracts/asd/asdRouter.sol` : `_swapOFTForNote`
- **Mechanism:** `uint128 amountConverted = uint128(_amount)` silently truncates amounts above `type(uint128).max`. `lzCompose` deposits the full `amountLD` into `ASDUSDC` and passes the full `amountUSDC` into `_swapOFTForNote`, but only the truncated amount is quoted to `calcImpact` and passed to `CrocSwapDex.swap`.
- **Impact:** For large amounts (or crafted `amountLD` values), only a partial swap executes while the compose flow treats the full `amountNote` return as if the entire balance was converted. Residual `asdUSDC` stays on the router and is stealable via compose hijacking; accounting between swap output and ASD mint/send can also break assumptions on downstream chains.

---

## Compose griefing via inflated `amountLD`

- **Location:** `contracts/asd/asdRouter.sol` : `lzCompose`
- **Mechanism:** The contract never checks `IERC20(_from).balanceOf(address(this)) >= amountLD` before `ASDUSDC.deposit(_from, amountLD)`. `amountLD` comes only from attacker-controlled `_message` bytes.
- **Impact:** An attacker can frontrun the legitimate compose with a message whose `amountLD` exceeds the router balance, causing `deposit` to revert and the entire `lzCompose` to fail. This can be repeated to deny execution of the intended compose (DoS), delaying or blocking the user’s bridge completion while tokens remain exposed on the router.

---

## Excess native fee (`msg.value`) is not returned to users

- **Location:** `contracts/asd/asdRouter.sol` : `lzCompose` / `_sendASD` / `_refundToken`
- **Mechanism:** On cross-chain sends, only `_payload._feeForSend` is forwarded to `IOFT.send`. There is no branch that returns `msg.value - _payload._feeForSend` to the user or `_cantoRefundAddress` on success. `_refundToken` only forwards native assets on explicit failure paths and only up to `msg.value` when `_nativeAmount <= msg.value`.
- **Impact:** Users who overpay LayerZero executor fees lose the surplus ETH permanently. There is no owner sweep for stranded ETH, so those funds are irrecoverable (user fund loss, not attacker profit).

---

## Happy-path ASD transfer can revert despite “must not revert” design

- **Location:** `contracts/asd/asdRouter.sol` : `_sendASD` (same-chain branch)
- **Mechanism:** The NatSpec on `lzCompose` states it “Cannot revert anywhere”, but the same-chain path calls `ASDOFT(...).transfer(_payload._dstReceiver, _amount)` directly. OpenZeppelin `ERC20.transfer` reverts on failure (e.g. zero address, balance shortfall, or non-standard receiver behavior).
- **Impact:** A reverting final transfer rolls back the entire compose, including prior swap and NOTE deposit steps. Depending on LayerZero compose retry semantics, this can strand bridged tokens on the router (exposed to compose hijacking) or cause repeated failed execution for users with incompatible receivers.

---

## `ASDOFT.burn` external call before state update (reentrancy surface)

- **Location:** `contracts/asd/asdOFT.sol` : `burn`
- **Mechanism:** `burn` calls `cNoteToken.redeemUnderlying(_amount)` (external Compound call that transfers NOTE to the contract) before `_burn(msg.sender, _amount)`. A malicious or callback-enabled token in the Compound market chain could reenter `mint`/`burn` while `asD` supply still reflects the pre-burn balance.
- **Impact:** Risk is low if NOTE and cNOTE are standard trusted Canto deployments, but the CEI violation is a real reentrancy surface. A compromised or malicious underlying in the cNOTE market could manipulate mint/burn accounting within a single transaction.

---

## `withdrawCarry` relies on potentially stale `balanceOfUnderlying`

- **Location:** `contracts/asd/asdOFT.sol` : `withdrawCarry`
- **Mechanism:** `maximumWithdrawable` is computed as `CTokenInterface(cNote).balanceOfUnderlying(address(this)) - totalSupply()`. In Compound v2, `balanceOfUnderlying` is a view that uses `exchangeRateStored`, not an accrual-updating call. The owner can withdraw based on a slightly stale exchange rate.
- **Impact:** In edge cases (rapid interest accrual or exchange-rate movement), the owner could withdraw marginally more carry than the contract can sustain at the updated rate, causing later `burn` calls to fail (`redeemUnderlying` reverts) and temporarily locking user redemptions until more backing is added. This is primarily an owner-trust / accounting-staleness issue rather than direct external theft.

---

## Summary

| Severity | Count | Primary issue |
|----------|-------|----------------|
| Critical | 1–2   | Permissionless `lzCompose` (+ arbitrary vault on hijacked compose) |
| High     | 1     | Silent refund failures via `transfer` |
| Medium   | 3–4   | `uint128` truncation, compose DoS, stuck ETH, happy-path revert |

The dominant fix for most theft and griefing vectors is enforcing that only the LayerZero endpoint (or a trusted executor) may call `lzCompose`, and that the compose payload is the one registered by LayerZero for that `guid`—not arbitrary calldata. Secondary hardening should include whitelisting `ASDOFT` vault addresses, using `SafeERC20` for all refunds, bounding/checking `amountLD` against actual balances, and returning unused `msg.value`.

I’m in **Ask mode**, so this is analysis only. Switch to **Agent mode** if you want patches or tests written for these findings.

