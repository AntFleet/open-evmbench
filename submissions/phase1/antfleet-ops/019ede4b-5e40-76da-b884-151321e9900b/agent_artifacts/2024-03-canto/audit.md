# Audit: 2024-03-canto

## Missing Access Control on `lzCompose`
- Location: `contracts/asd/asdRouter.sol` : `lzCompose`
- Mechanism: The `lzCompose` function is intended to be called exclusively by the LayerZero endpoint to process composed messages, but it completely lacks access control modifiers (e.g., `onlyEndpoint`). Furthermore, it does not verify if the calling OApp (`_from`) is a trusted peer or if the message originates from a valid LayerZero source chain. 
- Impact: Any external account or contract can directly call `lzCompose` with arbitrarily crafted parameters. An attacker can pass a whitelisted USDC address as `_from` and a malicious payload to intentionally trigger the `_refundToken` fallback path, draining any ERC20 tokens or native ETH held by the `ASDRouter` contract to an attacker-controlled `_refundAddress`.

## Arbitrary Contract Interaction via User-Supplied `_cantoAsdAddress`
- Location: `contracts/asd/asdRouter.sol` : `lzCompose` (and `_depositNoteToASDVault`, `_sendASD`)
- Mechanism: The `_cantoAsdAddress` is decoded directly from the user-supplied `composeMsg` payload without any validation, whitelisting, or verification that it is a legitimate ASD vault. The router then approves this arbitrary address to spend its NOTE tokens, calls its `mint` function via low-level `call`, and later calls its `transfer` function.
- Impact: An attacker can supply a malicious contract address as `_cantoAsdAddress`. The malicious contract can steal the router's approved NOTE tokens during the `mint` call (or drain all NOTE if it ignores the approval amount and uses `transferFrom`). Additionally, when the router calls `transfer` on this malicious contract in `_sendASD`, the attacker can execute arbitrary code (e.g., reentrancy or direct calls) to drain other tokens (like USDC or other OFTs) held by the router.

## Inverted Swap Direction Logic in `_swapOFTForNote`
- Location: `contracts/asd/asdRouter.sol` : `_swapOFTForNote`
- Mechanism: The `isBuy` parameter for the CrocSwap `swap` and `calcImpact` functions is incorrectly set to `!isNoteBase`. In CrocSwap, `isBuy = true` means buying the base token and selling the quote token. If the goal is to swap OFT for NOTE, and OFT is the base token (`isNoteBase = false`), the router should sell the base (OFT) and buy the quote (NOTE), meaning `isBuy` should be `false`. However, the code sets `isBuy = true`. Conversely, if NOTE is the base token, it sets `isBuy = false` (selling NOTE) instead of `true` (buying NOTE). 
- Impact: The swap direction is completely inverted. The router will attempt to sell NOTE to buy OFT instead of selling OFT to buy NOTE. This will cause the `calcImpact` check to fail (returning false) and the swap to revert or fail, completely breaking the core cross-chain swapping functionality of the router and forcing all valid messages to be refunded.

## Denial of Service / Message Stuck due to Reverts in `lzCompose`
- Location: `contracts/asd/asdRouter.sol` : `_refundToken` (called by `lzCompose`)
- Mechanism: The `_refundToken` function uses `payable(_refundAddress).transfer(_nativeAmount)` to send native tokens and `IERC20(_tokenAddress).transfer(...)` for ERC20 tokens. The `.transfer()` method for native tokens forwards only 2300 gas and will revert if the recipient is a smart contract that requires more gas or lacks a payable fallback. Similarly, ERC20 `transfer` can revert if the recipient is blacklisted (e.g., USDC) or is a reverting contract. LayerZero's `lzCompose` must never revert, as it will cause the message to fail and get stuck in the endpoint's failed message queue.
- Impact: If the user's `_cantoRefundAddress` or `_dstReceiver` is a smart contract or a blacklisted address, the refund or transfer will revert. This causes the entire `lzCompose` transaction to revert, permanently stucking the LayerZero message and requiring manual intervention by the protocol team to clear the queue, resulting in a Denial of Service for the user's funds.
