# Audit: 2024-03-taiko

## Bridge watchdog can forge message receipts
- Location: `packages/protocol/contracts/bridge/Bridge.sol` : `suspendMessages`, `processMessage`, `recallMessage`
- Mechanism: `suspendMessages(..., false)` writes `proofReceipt[msgHash].receivedAt = block.timestamp` for any arbitrary hash. `processMessage` and `recallMessage` treat any nonzero `receivedAt` as already proven and skip `_proveSignalReceived`.
- Impact: A compromised `bridge_watchdog` can fabricate cross-chain message receipts, then execute forged messages after the delay. This can mint bridged assets, release vault assets, invoke cross-chain callbacks, or recall value from bridge liquidity without a real source-chain message.

## Retriable messages bypass bans and suspensions
- Location: `packages/protocol/contracts/bridge/Bridge.sol` : `retryMessage`
- Mechanism: `processMessage` checks `addressBanned[_message.to]` and honors `proofReceipt` suspension state before invocation, but `retryMessage` only checks `messageStatus[msgHash] == RETRIABLE` and then calls `_invokeMessageCall` directly.
- Impact: Any already-retriable message can still be executed against a banned target or suspended message hash, bypassing the bridge watchdog’s emergency controls.

## Assignment hook can pull ERC20 fees from arbitrary approved users
- Location: `packages/protocol/contracts/L1/hooks/AssignmentHook.sol` : `onBlockProposed`
- Mechanism: ERC20 prover fees are paid with `safeTransferFrom(_meta.coinbase, _blk.assignedProver, proverFee)`. `params.coinbase` is proposer-controlled in `LibProposing.proposeBlock`, and the prover assignment signature does not bind or authorize the fee payer.
- Impact: An attacker can set `coinbase` to any victim that approved the hook for `assignment.feeToken`, assign themselves as prover, and drain the victim’s allowance to the attacker-controlled prover address.

## Random high-tier proof selection is skippable
- Location: `packages/protocol/contracts/L1/libs/LibProposing.sol` : `proposeBlock`; `packages/protocol/contracts/L1/hooks/AssignmentHook.sol` : `_getProverFee`; `packages/protocol/contracts/L1/tiers/MainnetTierProvider.sol` : `getMinTier`
- Mechanism: `meta.minTier` is sampled inside `proposeBlock`, but the proposal can still be made to revert afterward. A proposer can provide assignment `tierFees` only for cheap tiers; if the random sample requires an expensive tier, `_getProverFee` reverts and the proposal is discarded.
- Impact: Proposers can cheaply retry until the sampled tier is favorable, avoiding rare high-security proof requirements such as SGX+ZKVM and weakening the intended probabilistic security model.

## Guardian approvals do not bind liveness-bond return data
- Location: `packages/protocol/contracts/L1/provers/GuardianProver.sol` : `approve`; `packages/protocol/contracts/L1/libs/LibProving.sol` : `proveBlock`
- Mechanism: Guardian approvals are keyed by `keccak256(abi.encode(_meta, _tran))`, excluding `_proof.data`. But top-tier proof data has special meaning: `_proof.data == RETURN_LIVENESS_BOND` immediately returns the block liveness bond to the assigned prover.
- Impact: The final guardian submitting a threshold-approved transition can unilaterally change the bond outcome and return the assigned prover’s liveness bond even if the other guardians did not approve that economic action.

## L2 basefee issuance is repeatedly over-applied
- Location: `packages/protocol/contracts/L2/TaikoL2.sol` : `anchor`, `_calc1559BaseFee`
- Mechanism: `_calc1559BaseFee` subtracts issuance based on `_l1BlockId - lastSyncedBlock`, but `lastSyncedBlock` is only updated when state-root syncing crosses `BLOCK_SYNC_THRESHOLD`. Multiple L2 blocks anchored with the same or nearby L1 block id repeatedly subtract the same elapsed-L1-block issuance.
- Impact: A proposer can drive `gasExcess` and therefore L2 basefee down far below the intended EIP-1559 curve by producing repeated blocks before the sync threshold advances, underpricing L2 gas and enabling congestion/resource abuse.

## SGX attestation accepts arbitrary enclave code by default
- Location: `packages/protocol/contracts/automata-attestation/AutomataDcapV3Attestation.sol` : `_verifyParsedQuote`; `packages/protocol/contracts/verifiers/SgxVerifier.sol` : `registerInstance`
- Mechanism: `_checkLocalEnclaveReport` defaults to false. When disabled, `_verifyParsedQuote` verifies Intel quote/certificate validity but does not check that `mrEnclave` or `mrSigner` matches the intended Taiko prover enclave.
- Impact: Any valid SGX enclave can register its reported key as a trusted SGX prover instance, then submit accepted SGX-tier proofs for arbitrary transitions.

## SGX instance expiry can be bypassed by self-rotation
- Location: `packages/protocol/contracts/verifiers/SgxVerifier.sol` : `verifyProof`, `_replaceInstance`
- Mechanism: `verifyProof` accepts a prover-supplied `newInstance` and `_replaceInstance` resets `instances[id] = Instance(newInstance, block.timestamp)` without checking that the new key is different, unused, or freshly attested.
- Impact: A holder of a valid or compromised SGX instance key can keep refreshing trust indefinitely, defeating `INSTANCE_EXPIRY` and the intended key-rotation/side-channel containment model.

## Timelock withdrawal signatures are replayable and unscoped
- Location: `packages/protocol/contracts/team/TimelockTokenPool.sol` : `withdraw(address _to, bytes _sig)`
- Mechanism: The recovered authorization signs only `keccak256(abi.encodePacked("Withdraw unlocked Taiko token to: ", _to))`. It has no nonce, deadline, chain id, contract address, grant id, amount, or cost bound.
- Impact: Anyone holding one valid signature can replay it forever, across pool deployments and as future tokens unlock, forcing withdrawals to the signed `_to` address and charging the recipient’s approved `costToken` balance when applicable.

