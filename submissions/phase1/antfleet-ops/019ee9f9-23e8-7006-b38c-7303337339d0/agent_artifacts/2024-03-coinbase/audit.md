# Audit: 2024-03-coinbase

# Security Audit Report

Findings below are limited to **genuine logic/security issues** in the pasted codebase. Centralization/trust in `MagicSpend.owner()` is assumed by design and is not listed as a bug.

---

## ETH balance over-commitment (insolvency)

- **Location:** `MagicSpend.sol` : `validatePaymasterUserOp`
- **Mechanism:** Each successful paymaster validation only checks `address(this).balance >= withdrawRequest.amount` for **that single request**, then credits `_withdrawableETH[sender] += withdrawAmount - maxCost`. There is no global liability tracking or reservation. Multiple validated UserOps (different users or different nonces for the same user) can each pass the balance check against the **same** ETH pool and accumulate `_withdrawableETH` beyond what the contract actually holds.
- **Impact:** Later `postOp()` / `withdrawGasExcess()` transfers can fail or underpay. Users with valid owner signatures may not receive authorized funds; ordering determines who gets paid. A user who obtains multiple signed requests can accumulate `_withdrawableETH` across concurrent validations and drain the pool in the first `postOp()`, leaving others insolvent.

Vulnerable path:

```solidity
// validatePaymasterUserOp — per-request check only
if (address(this).balance < withdrawAmount) {
    revert InsufficientBalance(withdrawAmount, address(this).balance);
}
_withdrawableETH[userOp.sender] += withdrawAmount - maxCost;
```

---

## Cross-chain replay of UUPS upgrades

- **Location:** `CoinbaseSmartWallet.sol` : `validateUserOp` / `executeWithoutChainIdValidation` / `canSkipChainIdValidation`
- **Mechanism:** UserOps whose calldata starts with `executeWithoutChainIdValidation` recompute `userOpHash` **without chain ID** and require nonce key `REPLAYABLE_NONCE_KEY` (8453). `canSkipChainIdValidation()` whitelists `upgradeToAndCall`. A single owner signature on such a UserOp is valid on **every chain** where the wallet exists at the same deterministic address.
- **Impact:** An owner-signed upgrade executed on one chain can be replayed on all other chains, pointing every deployment at the same implementation (including a malicious one). An attacker who obtains one valid upgrade signature, or who tricks an owner into signing an upgrade intended for one chain, can compromise or brick wallets everywhere they are deployed.

Vulnerable path:

```solidity
if (bytes4(userOp.callData[0:4]) == 0xbf6ba1fc) {
    userOpHash = getUserOpHashWithoutChainId(userOp);
    // ...
}
// canSkipChainIdValidation includes:
|| functionSelector == UUPSUpgradeable.upgradeToAndCall.selector
```

---

## Cross-chain replay of owner-set changes

- **Location:** `CoinbaseSmartWallet.sol` : `validateUserOp` / `executeWithoutChainIdValidation` / `canSkipChainIdValidation`
- **Mechanism:** Same chain-ID-stripped validation path also whitelists `addOwnerAddress`, `addOwnerPublicKey`, and `removeOwnerAtIndex`. Any owner-signed replayable UserOp for those selectors is valid cross-chain.
- **Impact:** An owner addition signed for intended sync on Base can be replayed on Ethereum, Optimism, etc., adding an attacker-controlled owner (or removing an owner) on chains the signer did not intend. Full wallet takeover is possible on replayed chains if a malicious or unintended owner change is replayed.

---

## `postOp` cannot handle `PostOpMode.postOpReverted`

- **Location:** `MagicSpend.sol` : `postOp`
- **Mechanism:** ERC-4337 EntryPoint calls `postOp` a second time with `PostOpMode.postOpReverted` when the first `postOp` reverts (e.g., ETH transfer failure, OOG in recipient). This contract unconditionally `assert(mode != PostOpMode.postOpReverted)`, so the recovery callback always reverts.
- **Impact:** Failed first `postOp` settlement cannot be cleanly unwound via the mandated EntryPoint callback. Depending on EntryPoint behavior, this can leave paymaster accounting inconsistent with expectations, block normal postOp failure handling, and interact badly with the over-commitment issue above when transfers fail due to insufficient contract ETH.

```solidity
assert(mode != PostOpMode.postOpReverted);
```

---

## UserOp failure still releases withdrawable ETH

- **Location:** `MagicSpend.sol` : `postOp`
- **Mechanism:** `postOp` does not branch on `PostOpMode.opReverted`. After validation credits `_withdrawableETH`, if the sponsored UserOp **execution reverts**, `postOp` still deletes `_withdrawableETH[account]` and transfers `withdrawable + (maxGasCost - actualGasCost)` to the account.
- **Impact:** A user with a valid owner-signed withdraw request can submit a UserOp that always reverts in execution and still receive the authorized ETH withdrawal in `postOp`. If the sponsor/owner intended release to be conditional on successful execution (swap, mint, etc.), that invariant is broken and funds can be extracted without performing the intended action.

```solidity
// No check: if (mode == PostOpMode.opReverted) return;
uint256 withdrawable = _withdrawableETH[account] + (maxGasCost - actualGasCost);
delete _withdrawableETH[account];
SafeTransferLib.forceSafeTransferETH(account, withdrawable, ...);
```

---

## WebAuthn missing origin and `rpIdHash` verification

- **Location:** `WebAuthn.sol` : `verify` (used from `CoinbaseSmartWallet.sol` : `_validateSignature`)
- **Mechanism:** The verifier checks UP/UV flags, `"type":"webauthn.get"`, challenge substring, and the P-256 signature, but explicitly does **not** verify `clientDataJSON.origin` or `authenticatorData.rpIdHash` against an expected relying party. `CoinbaseSmartWallet` calls `WebAuthn.verify(..., requireUV: false)`.
- **Impact:** In a web context, a user can be phished into signing on a malicious origin while the on-chain verifier accepts the assertion. Any integration that treats passkey approval as proof the user intended a specific dApp/RP is vulnerable to cross-site signing and unauthorized wallet operations, despite a cryptographically valid signature.

---

## Passkey verification does not require user verification (UV)

- **Location:** `CoinbaseSmartWallet.sol` : `_validateSignature`
- **Mechanism:** WebAuthn verification is invoked with `requireUV: false`, so only the User Present (UP) bit is required, not User Verified (UV/biometrics/PIN).
- **Impact:** On authenticators that allow non-UV assertions, possession of the device (or malware on it) may suffice to authorize high-value wallet operations without biometric/PIN verification, weakening authentication versus standard WebAuthn “required” user verification policy.

---

## Malformed WebAuthn input can panic validation

- **Location:** `WebAuthn.sol` : `verify`
- **Mechanism:** `authenticatorData[32]` is read without checking `authenticatorData.length >= 33`. Similarly, `clientDataJSON.slice(...)` trusts caller-supplied `challengeIndex` / `typeIndex` without bounds validation.
- **Impact:** Malformed or adversarially indexed WebAuthn payloads cause a panic revert instead of returning `false`. For ERC-4337 this can turn signature failure into a validation revert (bundler DoS / simulation breakage). For ERC-1271, `isValidSignature` reverts instead of returning `0xffffffff`, which can break composable protocols expecting a boolean result.

---

## Wallet can be permanently bricked by removing all owners

- **Location:** `MultiOwnable.sol` : `removeOwnerAtIndex`
- **Mechanism:** Owners can remove entries at any index with no minimum-owner check. After all owners are removed, no one can pass `onlyOwner`, and `_validateSignature` has no valid owner to authorize UserOps or upgrades.
- **Impact:** A single owner (or compromised owner) can irreversibly lock the wallet: no further execution, upgrades, or owner recovery on-chain. Funds already in the wallet become inaccessible via normal wallet controls (only EntryPoint-mediated paths if any remain).

---

## `payPrefund` silently ignores prefund transfer failure

- **Location:** `CoinbaseSmartWallet.sol` : `payPrefund`
- **Mechanism:** After `validateUserOp`, the modifier sends `missingAccountFunds` to `msg.sender` (EntryPoint) via `call`, but discards failure with `pop(call(...))`.
- **Impact:** If the wallet lacks ETH to prefund the EntryPoint, validation may still return success/failure based only on signature while the EntryPoint expected a deposit. This can cause UserOp validation/execution failure in non-obvious ways and complicate griefing/debugging when accounts are underfunded (lower severity, but a real logic gap).

---

## Notes on reviewed areas **not** reported as vulnerabilities

| Area | Reason |
|------|--------|
| **FCL.sol** | P-256 ECDSA path appears appropriate for secp256r1 (prime-order curve); `WebAuthn` enforces low-`s` before calling FCL. No concrete exploitable edge case identified without a dedicated crypto review. |
| **Nonce burn on invalid paymaster sig/expiry** | `validatePaymasterUserOp` sets `validationData` sig-fail/expiry bits; EntryPoint v0.6 reverts on failed paymaster validation, rolling back `_nonceUsed` writes. Not a persistent griefing vector. |
| **`withdraw()` expiry after `_validateRequest`** | Entire tx reverts on expiry, so nonce is not persisted. |
| **ERC1271 replay protection** | `replaySafeHash()` correctly binds signatures to `address(this)` and `chainId` for off-chain ERC-1271 use. |
| **MagicSpend withdraw hash** | Includes `chainId` and `address(this)`; cross-chain replay of withdraw requests is prevented. |

---

### Severity summary

| Severity | Finding |
|----------|---------|
| **High** | ETH balance over-commitment |
| **High** | Cross-chain replay of `upgradeToAndCall` |
| **Medium** | Cross-chain replay of owner add/remove |
| **Medium** | `postOp` `postOpReverted` assert |
| **Medium** | Withdraw on failed UserOp execution |
| **Medium** | WebAuthn missing origin/`rpIdHash` checks |
| **Low–Medium** | `requireUV: false` for passkeys |
| **Low** | WebAuthn malformed-input panic |
| **Low** | Remove-all-owners bricking |
| **Low** | Silent `payPrefund` failure |

I can go deeper on any finding (e.g., concrete attack bundles for the insolvency issue or cross-chain replay PoC flows) if you want that next.

