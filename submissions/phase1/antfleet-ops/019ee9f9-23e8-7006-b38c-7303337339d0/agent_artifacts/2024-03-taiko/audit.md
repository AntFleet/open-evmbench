# Audit: 2024-03-taiko

# Taiko Protocol Security Audit Report

## QE identity bitmask checks use wrong operator precedence
- Location: `AutomataDcapV3Attestation.sol` : `_verifyQEReportWithIdentity`
- Mechanism: The intended checks are `(miscSelect & miscselectMask) == miscselect` and `(attributes & attributesMask) == attributes`, but Solidity parses `==` with higher precedence than `&`. The expressions are therefore evaluated as `miscSelect & (miscselectMask == miscselect)` and `attributes & (attributesMask == attributes)`. The right-hand side is a boolean (0 or 1), so the code either always fails QE identity validation when masks differ from expected values, or—if the owner configures `miscselectMask == miscselect` and `attributesMask == attributes`—only tests the least significant bit instead of the full masked fields.
- Impact: On-chain DCAP attestation used by `SgxVerifier.registerInstance` does not correctly enforce Intel QE identity fields. An attacker who can satisfy the weakened checks (or who benefits from misconfiguration) can register a malicious SGX instance address and then submit fraudulent block proofs through `SgxVerifier.verifyProof`, potentially proving invalid L2 state transitions and compromising rollup safety.

## Prover assignment signature omits fee-paying coinbase
- Location: `AssignmentHook.sol` : `hashAssignment` / `onBlockProposed`
- Mechanism: `hashAssignment` binds `metaHash`, `parentMetaHash`, `blobHash`, fee token, expiry, tier fees, and other fields, but it does not include `meta.coinbase`. The prover signs this hash, yet `onBlockProposed` charges the prover fee from `_meta.coinbase` via `safeTransferFrom(_meta.coinbase, _blk.assignedProver, proverFee)` when paying in ERC20. In `LibProposing.proposeBlock`, `params.coinbase` is fully attacker-controlled whenever the proposer sets a non-zero value (it defaults to `msg.sender` only when zero).
- Impact: A malicious block proposer can obtain a valid prover signature for an assignment, then propose a block with an arbitrary `coinbase` address. Any address that has approved the `AssignmentHook` (or a spender path it uses) can have ERC20 prover fees pulled without consent, enabling theft of approved tokens.

## Arbitrary `delegateBySig` during airdrop claims
- Location: `ERC20Airdrop.sol` : `claimAndDelegate`
- Mechanism: `claimAndDelegate` verifies the Merkle claim for `user`, transfers tokens to `user`, and then unconditionally executes `IVotes(token).delegateBySig(...)` using attacker-supplied `delegationData`. The contract comment acknowledges the delegation signature “may not correspond to the user address,” and there is no requirement that the recovered signer equals `user` or `msg.sender`.
- Impact: Anyone can call `claimAndDelegate` with their own valid claim proof while supplying a third party’s `delegateBySig` signature. This lets an attacker change another account’s vote delegation (governance capture/griefing) using a signature that was intended for a different context, without that account’s participation in the claim.

## Cross-chain replay of TimelockTokenPool withdrawal signatures
- Location: `TimelockTokenPool.sol` : `withdraw(address _to, bytes memory _sig)`
- Mechanism: Withdrawal authorization uses `keccak256(abi.encodePacked("Withdraw unlocked Taiko token to: ", _to))` with plain `ECDSA.recover`, and no EIP-712 domain separator, chain ID, contract address, or nonce. The same signature is valid on any deployment of the pool that shares the same signing key semantics.
- Impact: If `TimelockTokenPool` is deployed on multiple chains (or redeployed), a single off-chain signature authorizing withdrawal to `_to` can be replayed on every instance. An attacker can submit the same signature on another chain to trigger additional withdrawals for the same recipient, draining duplicate pool balances.

## SGX proof verification skipped in contesting mode
- Location: `SgxVerifier.sol` : `verifyProof`
- Mechanism: When `IVerifier.Context.isContesting` is true, `verifyProof` returns immediately without validating the SGX signature or instance rotation logic. `LibProving.proveBlock` sets `isContesting` whenever a proof is submitted at the same tier as the existing transition and that tier has a non-zero `contestBond`.
- Impact: At the SGX tier, any address can call `proveBlock` in contesting mode with arbitrary `_proof.data`, pay the contest bond, and set `ts.contester` without cryptographic evidence. This halts `LibVerifying.verifyBlocks` at that block (contested transitions block verification) and can be used to grief finalization or extort the protocol/economy until a higher tier resolves the dispute, with limited cost beyond the contest bond.

## USDC burn path ignores `transferFrom` return value
- Location: `USDCAdapter.sol` : `_burnToken`
- Mechanism: `_burnToken` calls `usdc.transferFrom(_from, address(this), _amount)` and then `usdc.burn(_amount)` without checking the boolean return value of `transferFrom`. Unlike `safeTransferFrom`, a `false` return does not revert.
- Impact: For ERC20 implementations that signal failure via `false` instead of reverting, a bridge burn can proceed and mint/release assets on the destination side even though no USDC was actually received by the adapter, causing a bridge accounting mismatch and potential unbacked minting of bridged assets.

## Liveness bond can be returned before block verification
- Location: `LibProving.sol` : `proveBlock`
- Mechanism: For top-tier proofs (`tier.contestBond == 0`), if `_proof.data` equals the `RETURN_LIVENESS_BOND` sentinel, the function transfers `blk.livenessBond` to `blk.assignedProver` and zeroes `blk.livenessBond` before transition state is finalized and before `LibVerifying.verifyBlocks` runs. Top-tier provers are not restricted by `_checkProverPermission` (it returns early when `contestBond == 0`).
- Impact: A top-tier prover (e.g., guardian path) can return the full liveness bond to the assigned prover immediately upon proof submission for a block that has not yet been verified on-chain. If that transition is later invalidated or the block never becomes canonical, the assigned prover may keep the liveness bond while the protocol’s intended bond-for-liveness enforcement is undermined.

## ERC20Airdrop2 withdrawal lacks reentrancy protection
- Location: `ERC20Airdrop2.sol` : `withdraw`
- Mechanism: `withdraw(address user)` performs an external `IERC20(token).transferFrom(vault, user, amount)` without the `nonReentrant` modifier used elsewhere in the airdrop contracts. State (`withdrawnAmount[user]`) is updated before the external call.
- Impact: If the token or vault implements transfer hooks (or malicious ERC20 behavior), a reentrant call during `transferFrom` can observe stale `withdrawnAmount` and withdraw the same vested allocation multiple times before state is fully persisted across reentrant executions, draining vault funds.

