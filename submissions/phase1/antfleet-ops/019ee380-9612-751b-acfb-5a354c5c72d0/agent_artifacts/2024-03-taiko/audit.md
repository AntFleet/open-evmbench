# Audit: 2024-03-taiko

Below are the issues I consider genuine security vulnerabilities after working through the codebase. I was unable to find a single obvious "critical" planted bug; the strongest defensible findings are access-control / cryptographic-binding issues. I'm reporting what I can justify from specific code paths rather than padding.

## SGX instance expiry can be bypassed indefinitely by self-rotation
- Location: `packages/protocol/contracts/verifiers/SgxVerifier.sol` : `verifyProof` / `_replaceInstance`
- Mechanism: `INSTANCE_EXPIRY` (180 days) is meant to bound how long a registered SGX key is trusted, with re-attestation required afterward. However, every successful `verifyProof` call recovers `oldInstance` from the proof signature and calls `_replaceInstance(id, oldInstance, newInstance)`, which writes `Instance(newInstance, uint64(block.timestamp))` — i.e. it resets `validSince` to "now" for an arbitrary, prover-chosen `newInstance` with no fresh on-chain remote attestation. Anyone holding a currently-valid instance key can therefore mint a fresh, full-lifetime successor key on each proof, so the expiry timer never actually forces re-attestation.
- Impact: A leaked or compromised SGX signing key cannot be aged out: as long as the holder keeps submitting proofs, they perpetually re-derive new valid instances and keep producing accepted SGX-tier proofs, defeating the time-bound trust assumption of the tier.

## Timelock withdrawal authorization signature is replayable and unbound
- Location: `packages/protocol/contracts/team/TimelockTokenPool.sol` : `withdraw(address _to, bytes _sig)`
- Mechanism: The recipient is recovered from `ECDSA.recover(keccak256(abi.encodePacked("Withdraw unlocked Taiko token to: ", _to)), _sig)`. The signed payload contains only the destination address — no nonce, no `address(this)`, and no `block.chainid`. The signature is not EIP-712 / domain-separated.
- Impact: A given signature is reusable across any deployment of this contract on any chain (multiple pools are explicitly deployed for investors/team/grantees), and cannot be revoked. Any third party who has seen one `withdraw` signature can re-submit it against another pool instance where the same recipient has an allocation, directing tokens to the address the recipient signed for once. The per-withdrawal amount is capped by the unlock schedule, but the cross-instance/cross-chain replay and irrevocability are real authorization weaknesses.

## `TaikoToken.burn` lets the owner burn arbitrary holders' balances
- Location: `packages/protocol/contracts/L1/TaikoToken.sol` : `burn(address _from, uint256 _amount)`
- Mechanism: `burn` is `onlyOwner` and calls `_burn(_from, _amount)` against any address, with no allowance or holder consent. Because TKO is also the bond/collateral and governance-voting token, the owner can unilaterally destroy any account's tokens (and thus their voting weight and posted bonds).
- Impact: This is an unconditional balance-confiscation primitive. If the owner key (or the governance/timelock that holds it) is compromised or malicious, it can wipe bonds, balances, and voting power of arbitrary users. At minimum this is an under-constrained privileged function; the destination of burns should be restricted (e.g. only contract-held bonds).

## Permissionless airdrop claim with caller-controlled delegation data
- Location: `packages/protocol/contracts/team/airdrop/ERC20Airdrop.sol` : `claimAndDelegate`
- Mechanism: `claimAndDelegate` is callable by anyone for any `user` present in the Merkle tree, and the `delegationData` (`delegatee, nonce, expiry, v, r, s`) is fully attacker-supplied. The code comment acknowledges the signature may not match `user`. While `delegateBySig` only delegates the recovered signer's votes (so an attacker cannot redirect the user's votes without the user's signature), an attacker can still force-claim on a user's behalf at an unfavorable snapshot block, and can burn/replay the legitimate `delegateBySig` nonce out from under the user (front-running the user's own delegation), causing the user's intended delegation transaction to revert on a consumed nonce.
- Impact: Griefing of delegation/voting setup and loss of user control over the timing of their claim and delegation. The same permissionless-claim shape exists in `ERC20Airdrop2.claim`.

## Notes (reviewed, judged not exploitable / by-design)
For completeness, I examined and do not consider vulnerabilities: the ETH-deposit ring buffer fee accounting in `LibDepositing` (the `ringBufferSize - 1` slack correctly reserves the fee slot), the hook-draining protection in `LibProposing.proposeBlock` (strictly-increasing hook ordering plus the post-loop TKO-balance check), the multi-hop trust chain in `SignalService.proveSignalReceived` (final value is checked against a locally-synced root), and the prover-permission / contest-bond math in `LibProving` (matches the intended bond economics).

