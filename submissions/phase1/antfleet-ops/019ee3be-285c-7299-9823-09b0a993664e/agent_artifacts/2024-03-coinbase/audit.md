# Audit: 2024-03-coinbase

## Nonce consumption before signature check
- Location: src/MagicSpend/MagicSpend.sol : withdraw
- Mechanism: `_validateRequest` (which marks `_nonceUsed[withdrawRequest.nonce][account] = true` and emits) is invoked unconditionally at the start of `withdraw`, before the subsequent `isValidWithdrawSignature` check (and before the `Expired` check).
- Impact: An attacker can submit a `WithdrawRequest` using any unspent nonce (with a garbage signature) to permanently consume that nonce for the target account, blocking all future legitimate withdrawals that rely on the same nonce.

## Signature check does not prevent nonce/state mutation in paymaster flow
- Location: src/MagicSpend/MagicSpend.sol : validatePaymasterUserOp
- Mechanism: `_validateRequest` (nonce marking + event) is executed before the `isValidWithdrawSignature` test that only later populates the `sigFailed` bit of `validationData`.
- Impact: A paymaster UserOp carrying a well-formed but incorrectly-signed `WithdrawRequest` will still consume the nonce and mutate `_withdrawableETH` (state changes are only rolled back on explicit revert paths such as `InsufficientBalance`); this enables nonce griefing and incorrect accounting even when the EntryPoint ultimately rejects the operation due to signature failure.

## Overly-permissive owner check enables self-authorized owner mutations
- Location: src/SmartWallet/MultiOwnable.sol : _checkOwner
- Mechanism: The `onlyOwner` modifier (used by `addOwner*`/`removeOwnerAtIndex`) returns successfully when `msg.sender == address(this)`.
- Impact: Any contract code path that performs an internal call (or a `delegatecall` that lands in the wallet) can add or remove owners without an external signature, allowing an attacker who can coerce a self-call to arbitrarily change the set of owners.

## FCL ecdsa_verify accepts points that are not proven to lie on the curve during scalar multiplication
- Location: src/FreshCryptoLib/FCL.sol : ecdsa_verify
- Mechanism: `ecAff_isOnCurve` is called only on the supplied public key `Q`; the subsequent `ecZZ_mulmuladd_S_asm` (Strauss-Shamir) never re-validates intermediate points `H = uG + vQ` or the base point `G`.
- Impact: A maliciously crafted `Q` (or exploitation of an edge case inside the assembly double/add routines) can cause the returned `x1` to satisfy the final `x1 == 0` predicate for a signature that would be rejected on a correct implementation, enabling signature forgery for WebAuthn fallbacks and any other caller of `ecdsa_verify`.
