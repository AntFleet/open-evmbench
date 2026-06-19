# Audit: 2024-03-taiko

## Bridge watchdog can forge message proofs
- Location: `packages/protocol/contracts/bridge/Bridge.sol` : `suspendMessages`, `processMessage`, `recallMessage`
- Mechanism: `suspendMessages(..., false)` sets `proofReceipt[msgHash].receivedAt = block.timestamp`. Both `processMessage` and `recallMessage` treat any nonzero `receivedAt` as proof that the message was received or failed, so the function skips `_proveSignalReceived` entirely. A `bridge_watchdog` can therefore “unsuspend” an arbitrary hash that was never proven.
- Impact: A compromised or over-privileged `bridge_watchdog` can execute forged cross-chain messages after the delay. Against vaults, this can mint bridged assets or release canonical assets by crafting a message whose context appears to come from the source-chain vault.

## Proposer can charge arbitrary ERC20 payer in assignment hook
- Location: `packages/protocol/contracts/L1/hooks/AssignmentHook.sol` : `onBlockProposed`
- Mechanism: For ERC20 prover fees, the hook transfers from `_meta.coinbase` to the assigned prover: `safeTransferFrom(_meta.coinbase, _blk.assignedProver, proverFee)`. `params.coinbase` is proposer-controlled in `LibProposing.proposeBlock`, and the prover’s assignment signature does not bind or authorize the fee payer. Any address that has approved the hook for the fee token can be selected as `coinbase`.
- Impact: An attacker/prover can drain ERC20 allowances from unrelated users who previously approved the assignment hook, by proposing blocks with `coinbase` set to the victim and fee paid to the attacker-controlled assigned prover.

## SGX attestation accepts arbitrary enclaves when local report checks are disabled
- Location: `packages/protocol/contracts/automata-attestation/AutomataDcapV3Attestation.sol` : `_verifyParsedQuote`; `packages/protocol/contracts/verifiers/SgxVerifier.sol` : `registerInstance`
- Mechanism: `_checkLocalEnclaveReport` defaults to false, and when disabled the attestation verifier never checks that the quote’s `mrEnclave` or `mrSigner` belongs to the intended Taiko prover enclave. `SgxVerifier.registerInstance` then accepts the reported address from any otherwise-valid SGX quote.
- Impact: If deployed in the default/disabled state, any valid SGX enclave can register an attacker-controlled signing key as a prover instance. The attacker can then submit SGX proofs for arbitrary transitions, compromising rollup state verification.

## Guardian proof approvals do not bind proof data
- Location: `packages/protocol/contracts/L1/provers/GuardianProver.sol` : `approve`; `packages/protocol/contracts/L1/libs/LibProving.sol` : `proveBlock`
- Mechanism: Guardian approvals are keyed only by `keccak256(abi.encode(_meta, _tran))`; `_proof.data` is not included. But `LibProving.proveBlock` gives top-tier proofs special economic behavior when `_proof.data == RETURN_LIVENESS_BOND`, returning the block liveness bond to the assigned prover before verification finalization.
- Impact: The final guardian submitting an already-threshold-approved proof can unilaterally alter bond handling and return the assigned prover’s liveness bond, even when the approved transition did not authorize that payout. This can bypass intended liveness-bond slashing/reward behavior.

## Tier randomness is proposer-skippable
- Location: `packages/protocol/contracts/L1/libs/LibProposing.sol` : `proposeBlock`; `packages/protocol/contracts/L1/tiers/MainnetTierProvider.sol` : `getMinTier`
- Mechanism: The required proof tier is derived from `block.prevrandao`, block number, and `numBlocks` during `proposeBlock`. These values are known before the proposer submits the transaction, so a proposer can simply avoid proposing in L1 blocks where the sampled tier is expensive, then retry in a later L1 block.
- Impact: Proposers can bias the random tier selection and avoid rare high-security proof requirements such as SGX+ZKVM sampling, weakening the intended probabilistic security model for proposed blocks.

