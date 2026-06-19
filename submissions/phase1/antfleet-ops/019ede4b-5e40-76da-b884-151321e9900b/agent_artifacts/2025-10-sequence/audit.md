# Audit: 2025-10-sequence

## Missing Access Control in Guest Contract
- Location: `src/Guest.sol` : `fallback`
- Mechanism: The `Guest` contract implements a `fallback` function that decodes `msg.data` into a payload and executes the contained calls via `_dispatchGuest` without any form of authentication, signature validation, or access control. 
- Impact: If the `Guest` contract is deployed on-chain and holds any assets (ETH, ERC20 tokens, NFTs) or is granted permissions, any external attacker can call it directly with a crafted payload to drain all funds or execute arbitrary actions on behalf of the contract.

## Missing Zero-Address Check in ecrecover
- Location: `src/modules/auth/BaseSig.sol` : `recoverBranch`
- Mechanism: When processing `FLAG_SIGNATURE_HASH` (0x00) and `FLAG_SIGNATURE_ETH_SIGN` (0x07), the code calls `ecrecover` to obtain the signer address but fails to verify that the returned address is not `address(0)`. In the EVM, `ecrecover` returns the zero address when given an invalid or malformed signature. (Notably, `SessionSig.sol` correctly implements this check, highlighting the omission here).
- Impact: If a wallet owner mistakenly configures `address(0)` as a signer in their multi-sig/image-hash tree, an attacker can bypass signature validation entirely by submitting an invalid signature. The `ecrecover` call will return `address(0)`, matching the configured leaf, adding the weight, and allowing the attacker to execute arbitrary transactions.

## Missing Zero-Address Check in Recovery Signer Validation
- Location: `src/extensions/recovery/Recovery.sol` : `isValidSignature`
- Mechanism: The `isValidSignature` function uses `ecrecover` to verify an ECDSA signature against a provided `_signer` address, but it does not check if `ecrecover` returns `address(0)` before comparing it to `_signer`. 
- Impact: If a recovery configuration includes `address(0)` as an authorized recovery signer, an attacker can submit a malformed/invalid signature. `ecrecover` will return `address(0)`, satisfying the `addr == _signer` condition, allowing the attacker to queue malicious payloads for recovery execution without possessing any valid cryptographic signature.
