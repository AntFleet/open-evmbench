# Audit: 2024-03-taiko

## Consensus findings

## Replayable, non-domain-separated withdrawal signature in TimelockTokenPool
*(consensus — Reviewer A and Reviewer B)*
- Location: `packages/protocol/contracts/team/TimelockTokenPool.sol : withdraw(address _to, bytes _sig)` and the helper `_withdraw`
- Mechanism: The authorization hash is `keccak256(abi.encodePacked("Withdraw unlocked Taiko token to: ", _to))`. It contains no nonce, no `block.chainid`, no contract address, no deadline, and no EIP-712/EIP-191 domain separation, and the function is permissionless (anyone may submit the signature). `_withdraw` then computes the currently-withdrawable amount, updates `amountWithdrawn`/`costPaid`, sends TKO from `sharedVault` to `_to`, and pulls `costToWithdraw` of `costToken` *from the recipient* via `safeTransferFrom(_recipient, sharedVault, costToWithdraw)`.
- Impact: A single captured signature is valid forever and is identical across every `TimelockTokenPool` deployment (multiple instances are deployed for investors/team/grantees). Anyone holding it can repeatedly force the recipient's currently- and later-unlocked tokens to be withdrawn to the fixed `_to` address at arbitrary times, and—when `costPerToken > 0`—force the recipient to spend their `costToken` allowance to "purchase" those unlocks whenever the attacker chooses, on every pool instance where that recipient has a grant. Because `_to` is fixed by the signer, this is griefing/timing-control loss and forced stablecoin spend rather than outright theft of the TKO to an attacker address, but the missing replay/domain protection is a genuine signature-handling flaw.

## Additional findings (single-reviewer)

## SGX enclave identity (MRENCLAVE / MRSIGNER) verification is disabled by default
*(Reviewer A only)*
- Location: `automata-attestation/AutomataDcapV3Attestation.sol` — state var `_checkLocalEnclaveReport` (defaults to `false`), the gated "Step 2" block in `_verifyParsedQuote`, and `toggleLocalReportCheck()`; reached via `SgxVerifier.registerInstance` → `IAttestation.verifyParsedQuote`
- Mechanism: The only place the quote's application enclave is bound to the trusted Taiko prover program is the block `if (_checkLocalEnclaveReport) { mrEnclaveIsTrusted = _trustedUserMrEnclave[...]; mrSignerIsTrusted = _trustedUserMrSigner[...]; if (!...) return (false, ...); }`. Because `_checkLocalEnclaveReport` is `false` after deployment (a private bool with no initializer, flipped only by the owner-only `toggleLocalReportCheck`), this entire identity check is skipped. The rest of `_verifyParsedQuote` only proves "this is a genuine, non-revoked Intel SGX platform with an acceptable TCB" — never *which program* the enclave runs.
- Impact: Until the operator explicitly calls `toggleLocalReportCheck()` *and* populates `_trustedUserMrEnclave`/`_trustedUserMrSigner`, an attacker who owns any genuine SGX machine can run an arbitrary enclave, produce a valid DCAP v3 quote, and pass `registerInstance`, becoming a trusted instance in `SgxVerifier`. They can then sign arbitrary (false) block transitions that `TIER_SGX` accepts as valid proofs. The higher-tier contestation game is the only backstop, so this defeats the standalone integrity of the SGX proof tier. It is a deploy-time-insecure default rather than an always-on bug, but a real, easy-to-miss configuration trap baked into the contract's default state.

## Unchecked ERC20 return values on configurable token transfers
*(Reviewer A only)*
- Location: `team/TimelockTokenPool.sol : _withdraw` (`IERC20(taikoToken).transferFrom(sharedVault, _to, amountToWithdraw)`); `team/airdrop/ERC20Airdrop.sol : claimAndDelegate` (`IERC20(token).transferFrom(vault, user, amount)`); `team/airdrop/ERC20Airdrop2.sol : withdraw` (`IERC20(token).transferFrom(vault, user, amount)`)
- Mechanism: These paths use raw `transfer`/`transferFrom` (not `SafeERC20`) on token addresses stored as mutable configuration (`taikoToken`, `token`). State that records the disbursement (`r.amountWithdrawn`, `r.costPaid`, `claimedAmount`, `withdrawnAmount`, `isClaimed`) is updated regardless of the transfer's boolean result.
- Impact: If any of these contracts is ever configured with a token that returns `false` on failure instead of reverting (a non-reverting/non-standard ERC20), the accounting advances as if the user was paid while the transfer silently failed, permanently desyncing internal balances from actual transfers and causing user loss. For the current TaikoToken (a compliant OZ ERC20 that reverts/returns true) this is latent rather than exploitable, but it is a real correctness/accounting hazard given the token address is not hard-coded.

## Arbitrary ERC20 fee payer in assignment hook
*(Reviewer B only)*
- Location: `packages/protocol/contracts/L1/hooks/AssignmentHook.sol : onBlockProposed`; `packages/protocol/contracts/L1/libs/LibProposing.sol : proposeBlock`
- Mechanism: `LibProposing.proposeBlock` lets the proposer set `params.coinbase` to any nonzero address, and `AssignmentHook.onBlockProposed` later uses `_meta.coinbase` as the ERC20 fee payer in `safeTransferFrom(_meta.coinbase, _blk.assignedProver, proverFee)`. The prover assignment signature does not bind or authorize this payer address.
- Impact: An attacker can set `coinbase` to a victim that has approved the hook for `assignment.feeToken`, then use a colluding assigned prover and signed assignment to transfer the victim's ERC20 allowance to the prover. Preconditions are a valid prover assignment and victim allowance/balance for the fee token.

## Guardian approvals do not bind liveness-bond return flag
*(Reviewer B only)*
- Location: `packages/protocol/contracts/L1/provers/GuardianProver.sol : approve`; `packages/protocol/contracts/L1/libs/LibProving.sol : proveBlock`
- Mechanism: Guardian approvals are keyed only by `keccak256(abi.encode(_meta, _tran))`, excluding `_proof.data`. However, `LibProving.proveBlock` gives `_proof.data == RETURN_LIVENESS_BOND` a special economic effect for top-tier proofs: it immediately returns the block's liveness bond to the assigned prover.
- Impact: A single malicious final guardian can reuse otherwise valid threshold approvals for a transition while choosing `_proof.data` that other guardians did not approve, returning the assigned prover's liveness bond and preventing that bond from being paid/slashed as the normal verification path would.

## Fractional paid grants can be undercharged
*(Reviewer B only)*
- Location: `packages/protocol/contracts/team/TimelockTokenPool.sol : getMyGrantSummary`
- Mechanism: Cost is computed from `amountUnlocked / 1e18` before multiplying by `costPerToken`, rounding the payable token amount down to whole TKO units. The withdrawal amount itself is still tracked at wei precision.
- Impact: A recipient can withdraw almost one full TKO more than they have paid for by leaving the final dust locked, or withdraw sub-1-TKO grants for zero cost. The loss is bounded to less than `costPerToken` per grant, but the rounding consistently favors the recipient.

