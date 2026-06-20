# Audit: 2024-03-taiko

## ERC20 assignment fees can be pulled from an arbitrary approved address
- Location: `packages/protocol/contracts/L1/hooks/AssignmentHook.sol` : `onBlockProposed`
- Mechanism: The ERC20 prover fee is pulled from `_meta.coinbase`, which is proposer-controlled via `BlockParams.coinbase`, but neither the prover assignment signature nor the hook checks that `_meta.coinbase` is `msg.sender` or otherwise authorized. An attacker can set `coinbase` to any victim that has approved `AssignmentHook` for the fee token, use themselves as `assignedProver`, sign their own assignment, and trigger `safeTransferFrom(_meta.coinbase, _blk.assignedProver, proverFee)`.
- Impact: Any standing ERC20 allowance granted to `AssignmentHook` can be drained to an attacker-controlled prover address through block proposals.

## SGX verifier accepts attestations from untrusted enclave code by default
- Location: `packages/protocol/contracts/automata-attestation/AutomataDcapV3Attestation.sol` : `_verifyParsedQuote`; `packages/protocol/contracts/verifiers/SgxVerifier.sol` : `registerInstance`
- Mechanism: `SgxVerifier.registerInstance` trusts `AutomataDcapV3Attestation.verifyParsedQuote`, but `_verifyParsedQuote` only checks the application enclave `MRENCLAVE`/`MRSIGNER` when `_checkLocalEnclaveReport` is enabled. That flag defaults to false, so any valid SGX quote with a valid Intel collateral chain can register the address embedded in `localEnclaveReport.reportData`, regardless of whether the enclave is the intended Taiko prover program.
- Impact: An attacker with any valid SGX enclave can register an arbitrary proving key and later submit SGX-tier proofs for arbitrary transitions, bypassing the intended trusted-enclave-code requirement.

## Withdrawal signatures are replayable and not scoped
- Location: `packages/protocol/contracts/team/TimelockTokenPool.sol` : `withdraw(address,bytes)`
- Mechanism: The signed message is only `keccak256("Withdraw unlocked Taiko token to: ", _to)`. It has no nonce, deadline, chain ID, contract address, grant identifier, amount, or cost bound. The same signature can therefore be replayed forever, across pools, and as additional tokens unlock.
- Impact: Anyone holding one valid recipient signature can repeatedly force withdrawals of all future unlocked grant tokens to the signed `_to` address and charge the recipient’s approved `costToken` balance whenever more tokens become withdrawable.

## Timelock admins can bypass the configured delay
- Location: `packages/protocol/contracts/L1/gov/TaikoTimelockController.sol` : `getMinDelay`
- Mechanism: `getMinDelay()` returns `0` whenever `msg.sender` has `TIMELOCK_ADMIN_ROLE`. OpenZeppelin timelock scheduling relies on `getMinDelay()` to enforce the minimum delay, so an admin can schedule operations with zero delay instead of the configured `_minDelay`.
- Impact: A timelock admin, or anyone compromising that role, can execute governance-controlled actions immediately, bypassing the intended timelock protection.

