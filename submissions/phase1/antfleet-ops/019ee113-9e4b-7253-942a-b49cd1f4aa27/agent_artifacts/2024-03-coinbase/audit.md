# Audit: 2024-03-coinbase

# Security Audit Report

## Missing signature malleability check in FCL `ecdsa_verify`
- Location: `src/FreshCryptoLib/FCL.sol` : `ecdsa_verify`
- Mechanism: The function validates `r` and `s` are in the range `[1, n-1]`, but it does not enforce that `s` lies in the lower half of the group order (i.e., `s <= n/2`). In standard ECDSA, given any valid signature `(r, s)`, the pair `(r, n - s)` is also a valid signature for the same message. Without the half-order check, signature malleability is possible: a valid signature can be transformed into another valid signature, which is a critical violation in contexts like Ethereum transaction signing.
- Impact: If this library is used directly to verify raw ECDSA signatures (outside the `WebAuthn` wrapper, which does enforce `s > P256_N_DIV_2`), an attacker can malleate a valid signature to produce a different valid signature. This can lead to replay attacks, broken nonce schemes, or duplicate valid signatures being accepted. Within the audited codebase, `WebAuthn.verify` guards against this, but the underlying FCL primitive is unsafe for direct use.

## Nonce consumed before signature/expiry validation in `MagicSpend.withdraw`
- Location: `src/MagicSpend/MagicSpend.sol` : `withdraw`
- Mechanism: The function calls `_validateRequest` first, which marks the nonce as used in the `_nonceUsed` mapping. Only after that does it check the signature validity and the expiry timestamp. If a user holds a valid signed `WithdrawRequest` that is already expired, calling `withdraw` will mark the nonce as consumed and then revert with `Expired()`. 
- Impact: This creates a griefing vector: anyone with a valid signature for a given nonce can permanently burn that nonce by submitting an expired request. The legitimate user (or paymaster owner) would need to issue a new signature with a different nonce, but the burned nonce is no longer usable. While the attacker must possess a valid signature (limiting the attack to parties who already received one), the contract should follow the check-effects-interactions pattern and validate all conditions before consuming the nonce.

## Missing `data.length` check in `executeWithoutChainIdValidation`
- Location: `src/SmartWallet/CoinbaseSmartWallet.sol` : `executeWithoutChainIdValidation`
- Mechanism: The function reads `bytes4(data[0:4])` to extract the selector, but it does not verify that `data.length >= 4` before doing so. If an EntryPoint (or future integration) were to call this function with calldata shorter than 4 bytes, the slicing operation would revert with an out-of-bounds panic.
- Impact: While the canonical EntryPoint v0.6 will not produce such calldata, the function is declared `public` and lacks the length guard. Any future code path or integration that calls this function with empty or short calldata will trigger a revert. This is a minor DoS / integration-fragility issue, not a direct theft vector, but it is a deviation from safe coding practices for a function that processes arbitrary calldata.

## `MagicSpend.validatePaymasterUserOp` does not cap `withdrawAmount` to contract balance for the user-settable portion
- Location: `src/MagicSpend/MagicSpend.sol` : `validatePaymasterUserOp`
- Mechanism: The function checks that `address(this).balance >= withdrawAmount`, but it does not check that the user's *cumulative* pending withdrawals (including this one) are within the contract's balance. The mapping `_withdrawableETH[userOp.sender]` is incremented by `withdrawAmount - maxCost` without bounding the total.
- Impact: If the paymaster owner signs multiple concurrent or sequential withdraw requests for the same user, the user's accumulated `_withdrawableETH` balance could grow beyond the contract's ETH balance. When the user later calls `withdrawGasExcess` or when `postOp` executes, the `safeTransferETH` / `forceSafeTransferETH` call could fail due to insufficient balance, causing the userOp to revert. This is a state-management bug that could lead to unexpected reverts and griefing.

## `FCL.ecdsa_verify` does not check that the public key is not the point at infinity
- Location: `src/FreshCryptoLib/FCL.sol` : `ecdsa_verify`
- Mechanism: The function calls `ecAff_isOnCurve(Qx, Qy)`, which rejects `(0, 0)`. However, the function does not reject the case where the public key has `y == 0` but `x != 0`. On the secp256r1 curve, points with `y == 0` are valid points (specifically, the point of order 2 and the identity represented differently), but the `ecAff_IsZero` helper considers any point with `y == 0` to be the identity. The `ecAff_add` function uses this convention.
- Impact: If a public key with `y == 0` is provided to `ecdsa_verify`, the `ecAff_isOnCurve` check passes (since such points are on the curve), but the subsequent scalar multiplication in `ecZZ_mulmuladd_S_asm` may produce incorrect results because the library treats `y == 0` as the identity. This is an edge case (the probability of a random key having `y == 0` is negligible), but it is a correctness issue for the library.
