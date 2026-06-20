# Audit: 2024-03-coinbase

 ## MagicSpend paymaster consumes nonces before signature/expiry checks
- Location: src/MagicSpend/MagicSpend.sol : validatePaymasterUserOp
- Mechanism: `_validateRequest` is called before `isValidWithdrawSignature` and before the `withdrawRequest.expiry` encoded in `validationData` is enforced by the EntryPoint. Because `validatePaymasterUserOp` returns a `sigFailed` `ValidationData` instead of reverting on an invalid signature, the state changes inside `_validateRequest` (marking the nonce used and emitting `MagicSpendWithdrawal`) persist even though the UserOperation will be rejected.
- Impact: An attacker can submit a `WithdrawRequest` with a valid unused nonce but an invalid signature or an expired timestamp. The EntryPoint rejects the operation, but the victim’s nonce is permanently consumed, rendering their legitimate owner-signed withdraw request unusable. Off-chain indexers can also be poisoned with spurious `MagicSpendWithdrawal` events.

## MagicSpend paymaster over-commits ETH without reserving liabilities
- Location: src/MagicSpend/MagicSpend.sol : validatePaymasterUserOp
- Mechanism: The balance check `address(this).balance < withdrawAmount` only verifies the contract’s immediate balance and ignores `_withdrawableETH` liabilities already granted to other validated UserOps. The function adds `withdrawAmount - maxCost` to `_withdrawableETH` without reserving those funds, so multiple operations can pass validation while their total committed amount exceeds the contract balance.
- Impact: An attacker with a valid owner-signed request can over-commit the paymaster’s ETH. During `postOp`, later transfers may fail because the contract is insolvent; `postOp` then asserts `mode != PostOpMode.postOpReverted`, so the EntryPoint’s recovery callback also reverts and can cause bundle failures, denying service to other users.

## WebAuthn verifier trusts caller-provided JSON field indices
- Location: src/WebAuthnSol/WebAuthn.sol : verify
- Mechanism: `verify` does not parse `clientDataJSON`; it relies on the caller-supplied `challengeIndex` and `typeIndex` and compares raw substrings of the JSON. A malicious client can embed the expected `"challenge":"<base64url(expected)>"` string (and similarly `"type":"webauthn.get"`) anywhere in `clientDataJSON`—for example inside another field—while the authenticator’s actual `challenge` field contains a different value.
- Impact: An attacker can reuse a WebAuthn assertion that the authenticator signed for one challenge/message as if it authenticated a different challenge/message. The signature verifies over the full `clientDataJSON`, and the substring check at the attacker-chosen index passes, allowing the attacker to bypass the challenge binding and forge authentication for arbitrary operations protected by passkey owners.
