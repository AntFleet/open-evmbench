# Audit: 2024-03-taiko

## 1. SGX attestation permanently broken due to invalid `mcopy` opcode

- **Location:** `packages/protocol/contracts/automata-attestation/utils/BytesUtils.sol` : `memcpy`
- **Mechanism:** The `memcpy` function attempts to use the `mcopy` assembly instruction, which is not a valid EVM opcode in Solidity 0.8.24. This causes a compilation failure or, if it somehow compiles, a runtime revert whenever `BytesUtils.substring` (or any other function that invokes `memcpy`) is called. The attestation library (`AutomataDcapV3Attestation`) heavily relies on `BytesUtils` for DER parsing and quote verification; every call path that needs to copy bytes will revert.
- **Impact:** The entire SGX‑based attestation and proof verification is dead. The `SgxVerifier` cannot register any new SGX instances, and no SGX proof can ever be verified. This breaks the SGX proof tier, potentially halting the protocol if blocks require SGX proofs.

## 2. Replayable signature allows indefinite withdrawal of future tokens

- **Location:** `packages/protocol/contracts/team/TimelockTokenPool.sol` : `withdraw(address _to, bytes memory _sig)`
- **Mechanism:** The signature over `"Withdraw unlocked Taiko token to: "` does not include a nonce, expiry, or any other mechanism to invalidate it after use. The same signature can be submitted multiple times, and each time it will withdraw all currently unlocked tokens to the designated `_to` address. Once a recipient signs such a message, an attacker who obtains the signature can continuously drain newly unlocked tokens forever without further consent.
- **Impact:** An attacker can steal all future unlocked tokens from a recipient who has ever signed a withdrawal message. This violates the expected one‑time authorisation model and can lead to total loss of the recipient’s vested tokens.
