# Audit: 2024-03-canto

## Unauthenticated compose execution lets attackers steal router-held tokens
- Location: `contracts/asd/asdRouter.sol` : `lzCompose`
- Mechanism: `lzCompose` is externally callable and does not authenticate `msg.sender` as the LayerZero endpoint/executor, nor does it verify that the supplied `_message` is the actual composed message for tokens delivered to the router. Before the whitelist check, malformed `composeMsg` flows into `_refundToken(_from, composeFrom, amountLD, ...)`, so attacker-controlled `_from`, `composeFrom`, and `amountLD` can transfer any token balance held by the router. On the happy path, attacker-controlled payload fields can redirect whitelisted OFT balances through swap/mint/send to attacker addresses.
- Impact: An attacker can front-run or retry after LayerZero deposits OFTs into the router and steal in-flight user funds, or drain any ERC20 balance accidentally or temporarily held by the router.

## Excess native tokens are permanently trapped on successful sends
- Location: `contracts/asd/asdRouter.sol` : `_sendASD`
- Mechanism: On successful Canto-local delivery, `_sendASD` uses none of `msg.value`. On successful cross-chain delivery, it forwards only `_payload._feeForSend` to `IOFT.send`. Any remaining native value is never refunded to `_cantoRefundAddress`, and the router has no withdrawal function.
- Impact: Any successful `lzCompose` call with `msg.value > 0` for Canto-local delivery, or `msg.value > _feeForSend` for cross-chain delivery, permanently locks the excess native tokens in `ASDRouter`.

## Short-paid or impaired USDC versions can drain good USDC reserves
- Location: `contracts/asd/asdUSDC.sol` : `deposit`, `withdraw`
- Mechanism: `deposit` mints fungible `asdUSDC` from the requested `_amount`, not from the actual balance delta received. The resulting `asdUSDC` is not tied to the deposited USDC version, and `withdraw` lets the holder choose any whitelisted version with sufficient recorded balance. For fee-on-transfer tokens, depegged bridge representations, or otherwise impaired whitelisted versions, the contract can mint full-value claims against less-than-full-value collateral.
- Impact: An attacker can deposit a weak or short-paid USDC version, receive fully fungible `asdUSDC`, and withdraw stronger USDC versions, shifting the loss to other wrapper depositors.

## Refund failure paths can leave bridged funds stuck
- Location: `contracts/asd/asdRouter.sol` : `_refundToken`
- Mechanism: The router’s failure recovery path uses raw `IERC20.transfer` without checking the returned boolean and uses native `transfer`, which reverts for refund contracts needing more than 2300 gas or rejecting native tokens. This contradicts the stated invariant that `lzCompose` must not revert and must refund on failures.
- Impact: A failed route can either silently fail to refund ERC20 tokens or revert while attempting the native refund, leaving LayerZero-delivered funds stuck in the router instead of recoverable by the intended refund address.

