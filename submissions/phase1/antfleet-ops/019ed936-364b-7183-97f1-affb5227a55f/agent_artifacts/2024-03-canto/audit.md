# Audit: 2024-03-canto

I have both reports inline and the task is a pure merge (no re-auditing, no inventing). Here is my mapping before writing:

- **A1** (refund-branch drain) + **A2** (happy-path hijack) ↔ **B1** (unrestricted `lzCompose` drain) → one consensus finding on the missing-auth drain.
- **A2** (arbitrary `_depositNoteToASDVault` call) ↔ **B3** (arbitrary ASD vault call) → one consensus finding.
- **A4** ↔ **B2** (uint128 truncation) → one consensus finding.
- **A3** (`_refundToken` revert/lock) and **A5** (asdUSDC decimals) → Reviewer A only.
- No Reviewer-B-only findings remain (B1/B2/B3 all reach consensus).

---

# Merged Security Audit Report — `contracts/asd/`

## Consensus findings

## Unauthenticated `lzCompose` allows draining and redirecting router-held tokens
*(consensus)*
- Location: `contracts/asd/asdRouter.sol` : `lzCompose` → `_refundToken` / `_sendASD` / `_depositNoteToASDVault` (roughly lines 72–250)
- Mechanism: `lzCompose` is `external payable` with no `require(msg.sender == endpoint)` and no trusted-OApp check that `_from` is the legitimate OFT that produced the composed message. Two concrete paths follow from this:
  - **Refund branch (any ERC-20):** the very first validation is `if (composeMsg.length != 224)`, whose failure branch executes `_refundToken(_guid, _from, OFTComposeMsgCodec.bytes32ToAddress(composeFrom), amountLD, msg.value, "Invalid composeMsg length")`. Here `_from` is a raw, unvalidated function argument and `amountLD`/`composeFrom` are decoded straight from attacker-supplied `_message`. `_refundToken` then performs `IERC20(_from).transfer(refundAddress, _amount)` — and this executes *before* the whitelist check on `_from` is ever reached, so the attacker can name **any** token the router holds.
  - **Happy path (whitelisted OFT redirect):** every routing parameter — `amountLD`, `_dstReceiver`, `_cantoAsdAddress`, `_cantoRefundAddress`, `_minAmountASD`, and the send fee — comes from the attacker-controlled compose payload. An attacker can call `lzCompose` (or front-run the legitimate executor delivery) whenever the router transiently holds whitelisted USDC OFT, routing the resulting ASD to their own receiver/refund address.
- Impact: Fully unauthenticated theft. Via the refund branch, anyone can drain the router's entire balance of any token (NOTE / asdUSDC / ASD / leftover USDC) with no precondition other than a nonzero balance. Via the happy path, an attacker can hijack and redirect in-flight bridged whitelisted OFT funds. The single critical fix is enforcing `require(msg.sender == endpoint)` plus validating `_from` against trusted OApps before any transfer.

## Arbitrary ASD vault call can redirect minted NOTE value
*(consensus)*
- Location: `contracts/asd/asdRouter.sol` : `_depositNoteToASDVault` and `_sendASD`, via the `lzCompose` payload field `_cantoAsdAddress` (roughly lines 129–160 and 198–207)
- Mechanism: `_cantoAsdAddress` is taken directly from the composed message and treated as the ASD vault, with no whitelist tying destination vaults to known ASDOFT contracts. `_depositNoteToASDVault` performs `IERC20(noteAddress).approve(_asdVault, _amountNote)` and then `_asdVault.call(mint…)` where `_asdVault = payload._cantoAsdAddress`; `_sendASD` subsequently transfers/sends tokens from that same attacker-chosen address. A malicious payload points `_cantoAsdAddress` at an attacker-controlled contract that implements `mint(uint256)`, pulls the freshly approved NOTE via `transferFrom` during the call, and returns success.
- Impact: An attacker can make the router grant NOTE allowance to, and invoke `mint` on, an arbitrary contract — stealing the NOTE value instead of minting legitimate ASD. Same precondition as above (router holding a whitelisted OFT balance, combinable with the unauthenticated `lzCompose` entrypoint).

## Silent `uint128` truncation in the swap path
*(consensus)*
- Location: `contracts/asd/asdRouter.sol` : `_swapOFTForNote` (`uint128 amountConverted = uint128(_amount);`, `uint128 uintMinAmount = uint128(_minAmountNote);`, roughly lines 213–247)
- Mechanism: `_amount` (the asdUSDC amount, already scaled up by `10**12` from 6-decimal USDC) and `_minAmountNote` are `uint256` values silently downcast to `uint128` with no bounds checks. If `_amount` exceeds `type(uint128).max`, the Ambient quote and swap execute for only the truncated low 128 bits while the router still holds/minted the full upstream asdUSDC amount. Separately, the slippage *check* uses the full-width `int(_minAmountNote)` (`minAmountInt`), but the swap call passes the **truncated** `uintMinAmount` as `minOut` — desynchronizing the validated slippage floor from the constraint actually submitted on-chain.
- Impact: The router can swap a different quantity than was deposited into `asdUSDC` (leaving excess funds stranded / stuck accounting), and/or the effective `minOut` can wrap to far below the validated floor, weakening slippage protection. Low likelihood at realistic token magnitudes, but a genuine arithmetic-safety defect — and more severe for very large bridge amounts or when combined with the unauthenticated `lzCompose`.

## Additional findings (single-reviewer)

## `_refundToken` breaks the "must never revert" invariant, permanently locking bridged funds
*(Reviewer A only)*
- Location: `contracts/asd/asdRouter.sol` : `_refundToken`, called throughout `lzCompose` / `_sendASD`
- Mechanism: The contract documents that `lzCompose` "cannot revert anywhere, must send the tokens to the intended receiver." But `_refundToken` uses raw `IERC20(_tokenAddress).transfer(...)` (return value ignored; reverts for non-standard tokens) and `payable(_refundAddress).transfer(_nativeAmount)`, which forwards only 2300 gas. If `_refundAddress` is a contract / smart-contract wallet needing more gas, or the token reverts on transfer, the entire `lzCompose` reverts. Because LayerZero compose messages cannot be retried with different logic, the bridged tokens become stuck in the router.
- Impact: The refund (failure-handling) path that is supposed to guarantee fund recovery can itself revert, permanently locking the user's bridged tokens — the exact failure mode the design tried to prevent. No attacker needed; a contract refund address or a slightly non-standard token triggers it.

## ASDUSDC decimal handling: division dust loss and underflow brick for >18-decimal tokens
*(Reviewer A only)*
- Location: `contracts/asd/asdUSDC.sol` : `withdraw` and `deposit`
- Mechanism: `withdraw` computes `amountToWithdraw = _amount / (10 ** (18 - usdcDecimals))`, truncating toward zero, while the burn removes the full `_amount` — so any non-multiple remainder is burned with no corresponding USDC payout, permanently stranding the dust in the contract (later sweepable only by the owner via `recover`). Separately, both `deposit` and `withdraw` compute `this.decimals() - ERC20(_usdcVersion).decimals()`; if a whitelisted version ever has more than 18 decimals, this `uint8` subtraction underflows and reverts, bricking deposits/withdrawals for that version.
- Impact: Minor per-call value leakage to the contract on non-aligned withdrawals, plus a configuration foot-gun that disables a version if a high-decimal token is whitelisted. Lower severity (rounding favors the contract, whitelist is owner-gated), but worth fixing by validating decimals and accounting for the truncated remainder.

---

*Merge notes:* Reviewer A's two separate write-ups of the missing-authentication issue (the `composeMsg.length != 224` refund-branch drain and the happy-path bridge hijack) were combined with Reviewer B's single drain finding into one consensus finding, preserving A's specific detail that the refund branch is reached **before** the `_from` whitelist check (enabling drain of *any* held token, not just whitelisted OFTs). All three of Reviewer B's findings reached consensus; the two refund-revert and asdUSDC-decimal findings are unique to Reviewer A.

