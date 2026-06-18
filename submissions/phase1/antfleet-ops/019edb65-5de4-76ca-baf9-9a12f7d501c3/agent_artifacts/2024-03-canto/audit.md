# Audit: 2024-03-canto

# Security Audit Report

## 1. Unsafe native token transfer breaks no-revert guarantee
- **Location:** `contracts/asd/asdRouter.sol` : `_refundToken`
- **Mechanism:** The function sends `_nativeAmount` to `_refundAddress` using `payable(_refundAddress).transfer(_nativeAmount)`. Solidity’s `.transfer()` forwards only 2300 gas, which is insufficient if the recipient is a contract whose fallback requires more than that. The `lzCompose` function is explicitly required *never to revert* (comment: “Cannot revert anywhere, must send the tokens to the intended receiver if something fails”). If this refund reverts due to out‑of‑gas, the whole `lzCompose` call reverts, leaving the original cross‑chain tokens stuck inside the router with no further recovery mechanism.
- **Impact:** An attacker (or any sender) can craft a compose message with `_cantoRefundAddress` set to a contract that consumes more than 2300 gas (e.g., by writing to storage or emitting complex events). If any downstream step fails, the refund attempt will revert, forcing `lzCompose` to revert and permanently locking the transferred tokens.

## 2. ABI decoding of swap return data can revert unexpectedly
- **Location:** `contracts/asd/asdRouter.sol` : `_swapOFTForNote`
- **Mechanism:** After the low‑level `call` to `crocSwapAddress` succeeds, the returned bytes are decoded with `abi.decode(data, (int128, int128))`. If the real CrocSwap pool returns data that does not match this exact tuple (e.g., due to an upgrade, a different pool type, or a custom implementation), `abi.decode` will throw. This exception propagates through `lzCompose` and violates the no‑revert assumption, even though the swap itself may have executed correctly.
- **Impact:** Cross‑chain messages that depend on the swap succeeding can become permanently frozen when the pool returns unexpected data. Users lose access to the swapped funds, and the router fails to fulfill its intended “always refund or forward” guarantee.
