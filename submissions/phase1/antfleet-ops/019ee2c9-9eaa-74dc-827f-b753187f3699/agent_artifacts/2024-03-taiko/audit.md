# Audit: 2024-03-taiko

## Forged bridge proofs via `suspendMessages`
- Location: `packages/protocol/contracts/bridge/Bridge.sol` : `suspendMessages`, `processMessage`, `recallMessage`
- Mechanism: `suspendMessages` lets the `bridge_watchdog` role write an arbitrary nonzero `proofReceipt[msgHash].receivedAt` for any chosen `msgHash`. Both `processMessage` and `recallMessage` interpret `receivedAt != 0` as “already proven” and skip their normal signal-proof checks. Calling `suspendMessages(..., false)` sets `receivedAt = block.timestamp`, which makes any attacker-chosen hash executable after the delay, or immediately on chains where `getInvocationDelays()` returns zero. Because the function operates on raw hashes and never verifies that the hash corresponds to a real proven message, the watchdog can fabricate bridge receipts out of thin air.
- Impact: A malicious or compromised `bridge_watchdog` can execute or recall arbitrary unproven messages, causing the bridge to release Ether, mint or unlock bridged assets through the vaults, or invoke privileged cross-chain callbacks without any legitimate source-chain message.

## SGX proof keys can self-renew forever
- Location: `packages/protocol/contracts/verifiers/SgxVerifier.sol` : `verifyProof`, `_replaceInstance`
- Mechanism: `verifyProof` accepts any `newInstance` embedded in `_proof.data`, and `_replaceInstance` blindly overwrites `instances[id]` with `Instance(newInstance, block.timestamp)`. There is no check that `newInstance` differs from the current key or has never been used before. A valid SGX instance can therefore submit a proof with `newInstance == oldInstance`, which refreshes `validSince` and resets the 180-day expiry without rotating to a fresh key. This breaks the intended one-time/rotating-key security model described in the contract comments.
- Impact: A compromised or leaked SGX proving key can remain valid indefinitely by periodically proving blocks and renewing itself, allowing long-term unauthorized use instead of expiring.

## Airdrop claims can consume arbitrary holders’ delegation signatures
- Location: `packages/protocol/contracts/team/airdrop/ERC20Airdrop.sol` : `claimAndDelegate`
- Mechanism: the claim proof authenticates only `(user, amount)`, but `delegationData` is forwarded directly into `IVotes(token).delegateBySig(...)` without checking that the recovered signer is the same as `user`. As a result, any valid Taiko delegation signature from any address can be executed during any claim. `delegateBySig` updates the signer’s delegation and consumes that signer’s nonce, so this contract acts as an open relay for unrelated holders’ voting permits.
- Impact: An attacker who obtains a valid delegation signature from another token holder can use any airdrop claim to redirect or grief that holder’s governance power, including votes tied to their existing balance, without their consent.

## Withdrawal signatures in `TimelockTokenPool` are replayable across time and deployments
- Location: `packages/protocol/contracts/team/TimelockTokenPool.sol` : `withdraw(address,bytes)`
- Mechanism: the signed message is only `keccak256("Withdraw unlocked Taiko token to: ", _to)`. It omits the pool address, chain ID, recipient identity, nonce, and expiry, and it is recovered as a raw ECDSA hash rather than a domain-separated EIP-712 payload. Any valid signature over that bare message can therefore be replayed indefinitely, and the same signature is valid against every `TimelockTokenPool` instance where the recovered recipient has a grant. Each replay withdraws the full currently unlocked amount for that recipient.
- Impact: Anyone holding one valid withdrawal signature can repeatedly pull every future unlocked tranche for that recipient to the signed address, and can reuse the same signature against other pool deployments that vest tokens to the same recipient.

