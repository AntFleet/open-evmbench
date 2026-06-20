# Audit: 2024-03-canto

 ## Ambient swap configured in the wrong direction and funded without DEX approval
- Location: `contracts/asd/asdRouter.sol` : `_swapOFTForNote`
- Mechanism: The function sets `bool isNoteBase = baseToken == noteAddress` and then passes `isBuy = !isNoteBase` to both `ICrocImpact.calcImpact` and `ICrocSwapDex.swap`. In Ambient, `isBuy == true` means the trader receives the base token; because the router wants to receive `NOTE` and pay `asdUSDC`, `isBuy` should be `isNoteBase` when `NOTE` is the base and `false` when `asdUSDC` is the base. The current flag is therefore inverted, causing the slippage check to evaluate the wrong flow sign and the swap to move funds in the unintended direction. The router also never `approve`s `asdUSDC` or `NOTE` for `crocSwapAddress`, so even with the correct direction the DEX cannot pull the input tokens.
- Impact: The OFT → ASD bridging flow through `lzCompose` cannot successfully swap into `NOTE`; the execution falls into the `swap failed` refund path, so users never receive the intended ASD tokens and the cross-chain minting functionality is permanently unavailable (Denial of Service).

## Refund transfers silently ignore ERC20 failures
- Location: `contracts/asd/asdRouter.sol` : `_refundToken`
- Mechanism: The function calls `IERC20(_tokenAddress).transfer(_refundAddress, _amount)` directly and does not check the returned `bool` or use `SafeERC20`. If the token returns `false` on failure (e.g., a non-standard or broken whitelisted USDC version, or an insufficient balance because a previous step already moved the funds), the call is treated as successful.
- Impact: A compose failure may emit a `TokenRefund` event while no tokens are actually transferred, permanently locking those funds in the router and making refund tracking unreliable for users and off-chain automation.

## `lzCompose` lacks LayerZero composer/endpoint authorization
- Location: `contracts/asd/asdRouter.sol` : `lzCompose`
- Mechanism: The function is public as required by `IOAppComposer` but has no `msg.sender` validation (e.g., `onlyEndpoint`/`onlyComposer`). The contract relies on the caller being the LayerZero executor, yet any address can directly invoke it with an arbitrary `_from` token and arbitrary compose data.
- Impact: An attacker can call `lzCompose` directly to trigger refund or processing logic against any tokens currently held by the router, replay/craft compose messages, and route refunds to an attacker-controlled `_cantoRefundAddress`, draining accidental or leftover balances and breaking the trust assumption that only LayerZero-validated messages drive state transitions.

## ASD vault address from the compose payload is never validated
- Location: `contracts/asd/asdRouter.sol` : `_depositNoteToASDVault`, `_sendASD`
- Mechanism: `payload._cantoAsdAddress` is passed straight into a low-level `mint` call and then into `ASDOFT(_payload._cantoAsdAddress).transfer` / `IOFT.send`. There is no whitelist or sanity check ensuring the address is a legitimate asdOFT/ASD vault.
- Impact: A malicious source sender can hard-code a fake `_cantoAsdAddress` whose `mint` returns success but mints nothing and whose `transfer`/`send` silently succeeds. The router will mark the cross-chain message as completed while the user receives no real ASD tokens, causing a total loss of the bridged stablecoin value.

## `asdOFT.withdrawCarry` checks external state before the reentrancy-sensitive external call
- Location: `contracts/asd/asdOFT.sol` : `withdrawCarry`
- Mechanism: `maximumWithdrawable = CTokenInterface(cNote).balanceOfUnderlying(address(this)) - totalSupply()` is read once at the start, then `CErc20Interface(cNote).redeemUnderlying(_amount)` is invoked. No reentrancy guard or CEI ordering is used, so if `cNote` (or a hookable NOTE underlying) reenters before its own internal balances are updated, the second call recomputes `balanceOfUnderlying` using the pre-redemption value while `totalSupply()` is unchanged.
- Impact: A compromised or reentrant cToken can force repeated redemptions against a stale `maximumWithdrawable`, allowing withdrawal of more than the accrued carry and breaking the 1:1 NOTE backing invariant.

## Direct external calls in `lzCompose` can revert and lock funds
- Location: `contracts/asd/asdRouter.sol` : `lzCompose`, `_sendASD`
- Mechanism: Although swap failure, vault-mint failure, and cross-chain send failure are wrapped in low-level calls that fall back to a refund path, `ASDUSDC(asdUSDC).deposit(_from, amountLD)` at the start and `ASDOFT(_payload._cantoAsdAddress).transfer(_payload._dstReceiver, _amount)` on the Canto destination path are direct external calls. If either reverts (paused token, blacklisted/reverting receiver, out-of-gas receiver hook, etc.), the entire `lzCompose` transaction reverts despite the comment requiring it to never revert.
- Impact: A specially crafted payload can cause the compose to revert after the user's OFT/asdUSDC has already been moved into the router or after NOTE has already been deposited into a malicious/faulty ASD vault, leaving tokens stuck in the router with no recovery function.
