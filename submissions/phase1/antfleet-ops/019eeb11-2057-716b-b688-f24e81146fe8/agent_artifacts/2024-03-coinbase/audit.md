# Audit: 2024-03-coinbase
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Cross-chain replay of `removeOwnerAtIndex` removes the wrong owner
*(consensus, 4 of 6 reports)*
- Location: `src/SmartWallet/MultiOwnable.sol` : `removeOwnerAtIndex`, together with `src/SmartWallet/CoinbaseSmartWallet.sol` : `executeWithoutChainIdValidation` / `canSkipChainIdValidation` / `validateUserOp`
- Mechanism: `removeOwnerAtIndex` identifies the victim owner purely by numeric `index`, with no parameter binding the call to *which* owner key the signer intended to remove. The selector is whitelisted in `canSkipChainIdValidation`, so the UserOp is hashed via `getUserOpHashWithoutChainId` (chain ID deliberately excluded) and the signature is valid on every chain that shares the wallet address. Owner indices (assigned by a per-chain `nextOwnerIndex++`) diverge across chains whenever the wallet was initialized with a different owner set, or owners were added/removed via the non-replayable `execute` path on one chain, or replayable ops were applied in a different order. A replayed `removeOwnerAtIndex(i)` then deletes a different owner on each chain.
- Impact: An owner who signs "remove index `i`" to revoke a compromised key on chain A has it replayed on chain B, where index `i` maps to a different, still-trusted owner — silently revoking the wrong key (or failing to revoke the compromised one), or removing a recovery/security key, or even the last usable owner causing lockout. Because the replay path enforces sequential `REPLAYABLE_NONCE_KEY` nonces, a `NoOwnerAtIndex` revert also stalls the sequential nonce and blocks further cross-chain owner synchronization. This is the exact reason production later changed the signature to `removeOwnerAtIndex(uint256 index, bytes calldata owner)` and asserted `ownerAtIndex(index) == owner`.
- Reviewer disagreement: opus-4-8 shot 3 reviewed the chainless-execution/whitelist path and reported no vulnerability (cleared it on access-control grounds, without singling out index divergence).

## Cross-chain replay of `upgradeToAndCall` installs unintended/malicious implementation
*(consensus, 4 of 6 reports)*
- Location: `src/SmartWallet/CoinbaseSmartWallet.sol` : `validateUserOp` / `executeWithoutChainIdValidation` / `canSkipChainIdValidation` (selector `UUPSUpgradeable.upgradeToAndCall`)
- Mechanism: `canSkipChainIdValidation` whitelists `upgradeToAndCall`, and the chainless hash (`getUserOpHashWithoutChainId`) binds only the calldata and EntryPoint address — not the destination chain or the implementation's code identity. The signed payload commits only to a 20-byte implementation address; there is no codehash check. The same address can point to different or attacker-controlled code on a different chain.
- Impact: Anyone who observes a valid chainless `upgradeToAndCall` UserOperation can replay it on any other chain where the same wallet address exists and the replayable nonce is unused. If that implementation address hosts different/attacker-controlled code on the target chain, the wallet is upgraded to malicious logic and the attacker takes full control of the account and its assets.
- Reviewer disagreement: opus-4-8 shot 3 cleared the chainless upgrade path on access-control grounds (whitelist + `onlyEntryPoint`) and reported no vulnerability; opus-4-8 shot 1 raised this mechanism only inside its `removeOwnerAtIndex` finding.

## `removeOwnerAtIndex` can remove the last owner and permanently brick the account
*(consensus, 2 of 6 reports)*
- Location: `src/SmartWallet/MultiOwnable.sol` : `removeOwnerAtIndex` (and `_initializeOwners` / `_addOwner`, which never track an owner count)
- Mechanism: The function only checks that *something* exists at the index (`owner.length == 0`); there is no guard preventing removal of the final remaining owner and no owner-count invariant anywhere in `MultiOwnable`. Every privileged entrypoint (`execute`, `executeBatch`, `addOwnerAddress`, `addOwnerPublicKey`, `removeOwnerAtIndex`, `_authorizeUpgrade`) ultimately gates on `_checkOwner()`.
- Impact: Removing the last owner is irreversible — the `isOwner` mapping is empty, every `ownerAtIndex` returns empty bytes, `_checkOwner()` always reverts, and `_validateSignature` can never resolve a signer. No one can add an owner, execute calls, or run a UUPS upgrade; the account and all assets are permanently frozen. Reachable by a single owner self-removing, by a malicious co-owner removing all others to seize sole control, and cross-chain via the replay above (a removal that legitimately leaves ≥1 owner on chain A can be the last owner on chain B). Production added a dedicated `removeLastOwner` and a last-owner guard.
- Reviewer disagreement: opus-4-8 shot 3 acknowledges the missing last-owner guard but classifies it as intended/by-design (requires owner privileges, "documented design of this version"). *(conflicting reviews: 1 of 6 reports defended this code path)*

## Minority findings

## Zero expiry becomes forever-valid in the paymaster flow
*(minority, 1 of 6 reports)* *(conflicting reviews: 3 of 6 reports defended this code path)*
- Location: `src/MagicSpend/MagicSpend.sol` : `validatePaymasterUserOp` and `withdraw`
- Mechanism: `withdraw()` treats `expiry == 0` as expired (`block.timestamp > withdrawRequest.expiry` reverts). The paymaster path performs no such check and instead packs `withdrawRequest.expiry` into ERC-4337 `validationData`. In EntryPoint v0.6, `validUntil == 0` means "no expiry," so a request that is invalid for direct withdrawal becomes indefinitely valid through `validatePaymasterUserOp`.
- Impact: If the owner signs or accidentally issues a withdraw request with `expiry = 0`, an attacker holding that request can redeem it forever through the paymaster path (subject to the signed amount/nonce and contract balance).
- Reviewer disagreement: opus-4-8 shots 1, 2, and 3 each examined the expiry handling and cleared it as sound (`uint256(expiry) << 160` is widen-only and correctly placed in the `validUntil` bits 160–207), without flagging the `expiry = 0` → no-expiry semantics.

## Paymaster refunds gas before charging its own postOp cost
*(minority, 1 of 6 reports)* *(conflicting reviews: 3 of 6 reports defended this code path)*
- Location: `src/MagicSpend/MagicSpend.sol` : `validatePaymasterUserOp` / `postOp`
- Mechanism: `validatePaymasterUserOp` reserves `maxCost` from the signed withdrawal, but `postOp` refunds `maxGasCost - actualGasCost` to the account. In EntryPoint v0.6 the `actualGasCost` passed into `postOp` is computed before the paymaster's own `postOp` execution is measured, so MagicSpend refunds too much and never deducts its own post-operation gas from the signed withdrawal amount.
- Impact: A user with a valid signed paymaster withdrawal can receive `amount - prePostOpGasCost` while MagicSpend's EntryPoint deposit separately pays the `postOp` gas. Repeating this drains paymaster-controlled funds beyond the owner-signed amounts, especially when ETH delivery to the recipient takes the expensive forced-transfer path.
- Reviewer disagreement: opus-4-8 shots 1, 2, and 3 each computed the postOp refund as exactly netting to `amount − actualGasCost` (with the paymaster paying `actualGasCost`) and found no over-refund.

---

*Reconciliation check: 5 distinct findings identified across the 6 input reports (by code path + root cause) — owner-removal replay, upgrade replay, last-owner brick, zero-expiry paymaster, postOp over-refund — and all 5 appear in this output. The two opus-4-8 "owner-edit replay" findings were merged into the owner-removal consensus entry (same code path + root cause); the upgrade-replay and owner-removal-replay entries are kept separate because they target different selectors (`upgradeToAndCall` vs `removeOwnerAtIndex`) with different root causes and impacts. The MagicSpend within-bundle balance over-commitment, mentioned only by opus-4-8 shots 2 and 3 and explicitly dismissed by both as not a vulnerability, is claimed as a finding by no report and is therefore not listed.*

