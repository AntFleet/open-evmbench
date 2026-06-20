# Audit: 2024-03-taiko

Here is the security audit of the provided Solidity codebase.

## 1. Replay Attack & Multiple Liveness Bond Draining via Signature Reuse
- Location: `AssignmentHook.sol` : `onBlockProposed` & `LibProposing.sol` : `proposeBlock`
- Mechanism: `AssignmentHook` does not record any state or tracking information to prevent signature reuse (such as nonces or tracked hashes). Provers can sign a `ProverAssignment` where `metaHash` is set to `0` to allow flexibility in block assignments. This signature becomes valid for any proposed block that references the same `_blobHash`. A malicious block proposer can intercept this signature and replay it across multiple block proposals by leveraging the same `_blobHash` (either via blob reuse or by submitting multiple blocks in the same L1 transaction/txList).
- Impact: A malicious proposer can replay a prover's signature to propose an arbitrary number of blocks, forcing the victim prover to pay the liveness bond of 250 TKO multiple times. The prover's TKO tokens will be pulled and locked across numerous blocks, and since they cannot generate cryptographic proofs for all replayed blocks within the proving window, their liveness bonds will be forfeited.

## 2. Cross-Chain and Cross-Contract Signature Replay
- Location: `TimelockTokenPool.sol` : `withdraw(address, bytes)`
- Mechanism: The signature-based `withdraw` function allows any caller to trigger a withdrawal on behalf of a recipient to a destination address (`_to`). The signature hash is computed as `keccak256(abi.encodePacked("Withdraw unlocked Taiko token to: ", _to))`. This hash completely lacks the contract's own address (`address(this)`) as well as the chain identifier (`block.chainid`).
- Impact: A malicious actor can locate a valid signature from a user on a testnet deployment or a specific pool instance and replay it on mainnet or other deployments. This forces the recipient's tokens to be moved to `_to` on other networks or pools without their consent, potentially leading to a permanent loss of funds if the `_to` address is not secure, does not exist, or cannot receive tokens on those domains.

## 3. Bricked Cross-Chain Ownership and Governance
- Location: `CrossChainOwned.sol` : `onMessageInvocation`
- Mechanism: `CrossChainOwned` executes administrative transactions forwarded by a remote owner via `address(this).call(txdata)`. To authorize this execution, the contract validates that the source sender is the owner (`ctx.from == owner()`). However, when executing the payload via a low-level call to itself, the `msg.sender` of this sub-call is set to `address(this)`. Any function protected by the `onlyOwner` modifier (such as `setConfigAndExcess` in `TaikoL2EIP1559Configurable.sol`) checks if `msg.sender == owner()`. Since `address(this) != owner()`, the validation fails.
- Impact: The cross-chain ownership and governance mechanism is completely broken. Any remote transaction intended to configure parameters or trigger state changes protected by `onlyOwner` will persistently revert, bricking contract administration on L2.

## 4. Bridged Tokens Stuck/Locked Indefinitely If Recipient Contract Rejects Ether
- Location: `ERC20Vault.sol`, `ERC721Vault.sol`, `ERC1155Vault.sol` : `onMessageInvocation`
- Mechanism: When processing a bridge message that transfers both tokens (ERC20/NFTs) and Ether (`msg.value > 0`), the `onMessageInvocation` function of the vault contracts first transfers the tokens and then immediately forces an Ether transfer to the target address via `to.sendEther(msg.value)`.
- Impact: If the recipient `to` address is a smart contract (such as a multisig, a liquidity pool, or custom wallet) that does not accept raw Ether, `to.sendEther` will revert and fail the entire message invocation. This sets the message status to `RETRIABLE`. Consequently, retrying will always fail, and since the message is `RETRIABLE` and not `FAILED`, the user cannot trigger a `recallMessage` on the source chain, permanently locking both the bridged tokens and the Ether in the vaults.
