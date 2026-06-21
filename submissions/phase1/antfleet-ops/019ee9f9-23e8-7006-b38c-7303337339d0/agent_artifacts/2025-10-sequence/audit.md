# Audit: 2025-10-sequence

Security audit of the provided Sequence wallet codebase. Findings below are limited to exploitable logic, access control, accounting, and validation flaws (not style/gas).

---

## Unauthenticated arbitrary execution in Guest

- **Location:** `Guest.sol` : `fallback` / `_dispatchGuest`
- **Mechanism:** The fallback decodes `msg.data` as a packed call batch and executes every call (with value) with no signature, nonce, or caller check. Delegatecalls are blocked, but ordinary external calls are not.
- **Impact:** Anyone can make `Guest` call arbitrary targets as `msg.sender == Guest`. If the contract holds ETH, it can be drained. Even with zero balance, it can be abused as an anonymous execution relay (e.g., triggering `onlyGuest`-style logic elsewhere, griefing, or probing integrations).

---

## Unauthenticated arbitrary execution in Simulator

- **Location:** `Simulator.sol` : `simulate`
- **Mechanism:** `simulate` is `external`, has no auth, and performs real `call` / `delegatecall` (including `delegatecall` into `IDelegatedExtension` handlers). It inherits `Stage2Module` storage layout, so delegatecalls can mutate simulator storage.
- **Impact:** Any user can execute attacker-chosen code in the simulator’s context, move any ETH held by the contract, and corrupt simulator state. Misuse as an on-chain “simulator” with funds or sensitive state is a full compromise.

---

## Stale-signature replay and nonce desync in Estimator

- **Location:** `Estimator.sol` : `estimate`
- **Mechanism:** Unlike `Calls.execute`, `estimate` does:

  ```solidity
  _consumeNonce(decoded.space, readNonce(decoded.space));
  ```

  instead of `_consumeNonce(decoded.space, decoded.nonce)`. It also consumes/increments the nonce **before** `signatureValidation`. A signature is bound to `decoded.nonce` inside `opHash`, but consumption is bound to the **current** on-chain nonce. When `decoded.nonce != readNonce(space)`, a signature for an old nonce can still validate while the contract advances the live nonce.

- **Impact:** On an `Estimator` deployment, an attacker can replay outdated signed payloads (wrong op, wrong batch) while desynchronizing nonce state. Combined with real execution in `_estimate`, this can move ETH, run delegatecalls, and brick future estimates/executions on that contract.

---

## Image-hash check bypass in Estimator

- **Location:** `Estimator.sol` : `_isValidImage`
- **Mechanism:** The override calls `super._isValidImage` and then unconditionally `return true`, so `signatureValidation` never rejects a recovered `imageHash`, regardless of wallet configuration.
- **Impact:** Any signature tree that meets weight/threshold is accepted on the Estimator instance, even if its Merkle root does not match the Estimator’s configured image hash. This widens replay/cross-configuration abuse on that contract (especially alongside the nonce bug above) and is unsafe if Estimator shares signer material with production wallets.

---

## Estimator performs real state-changing execution during “estimate”

- **Location:** `Estimator.sol` : `estimate` / `_estimate`
- **Mechanism:** `_estimate` mirrors production execution: external calls with `value`, delegatecalls to extensions, nonce consumption, and events—but is marketed as gas estimation.
- **Impact:** Callers/integrators treating `estimate` as read-only can unintentionally execute transfers, approvals, and storage updates. An attacker who can pass signature checks (easier due to `_isValidImage` bypass) can use `estimate` as a write path.

---

## Session permission bypass via out-of-bounds calldata reads

- **Location:** `PermissionValidator.sol` : `validatePermission` (via `LibBytes.readBytes32`)
- **Mechanism:** `LibBytes` explicitly does not bounds-check offsets. For short `call.data`, `readBytes32(rule.offset)` reads zero/padding. Rules using `LESS_THAN_OR_EQUAL` (and some `NOT_EQUAL` / masked `EQUAL`) can succeed on truncated calldata that does not actually encode the intended function arguments.
- **Impact:** A compromised session key can authorize a “max amount” rule, then execute a call with too-short calldata so the decoded amount reads as `0` and passes `<= limit`, while the target contract may still interpret the call differently—or combine with permissive targets to move tokens/value beyond the policy intent. This is a policy bypass on explicit sessions.

---

## Duplicate session signer entries create ambiguous / weaker permissions

- **Location:** `ExplicitSessionManager.sol` : `_validateExplicitCall`
- **Mechanism:** When multiple `SessionPermissions` entries share the same `signer`, validation always uses the **first** match in `allSessionPermissions`. The per-call `sessionPermission` index applies to that first entry’s `permissions` array only.
- **Mechanism detail:** A configuration tree can legally contain duplicate signer nodes (image hash still commits to both). The signer can pick `sessionPermission` indices against a weaker first node while the wallet owner believed a stricter later node governed behavior.
- **Impact:** Session policies can be weaker than the wallet config visually suggests; a session key may gain permissions the owner did not intend if duplicate signer leaves are ordered incorrectly.

---

## Shared nonce spaces between sessions and normal wallet execution

- **Location:** `SessionManager.sol` : `recoverSapientSignature` + `Calls.sol` : `_consumeNonce`
- **Mechanism:** Sessions are restricted to `space <= MAX_SPACE`, but the main wallet uses the same nonce mapping for those spaces. There is no reservation separating “session space” from “owner space.”
- **Impact:** A session key and the owner (or two sessions) using the same `space` can grief each other by consuming nonces, invalidating in-flight operations—denial-of-service on wallet execution, not direct theft by itself.

---

## Recovery queue unbounded growth (griefing)

- **Location:** `Recovery.sol` : `queuePayload`
- **Mechanism:** `queuedPayloadHashes[_wallet][_signer].push(payloadHash)` has no cap. Any party with a valid signer approval can enqueue unique payloads.
- **Impact:** An attacker can inflate the queue for `(wallet, signer)` pairs, causing griefing/DoS for recovery UX and on-chain indexers/wallets scanning the queue. No direct fund theft, but can delay or complicate recovery operations.

---

## WebAuthn / passkey RP binding not enforced on-chain

- **Location:** `Passkeys.sol` : `recoverSapientSignatureCompact` + `WebAuthn.sol` : `verify`
- **Mechanism:** The verifier deliberately skips `rpIdHash` and origin checks (documented in `WebAuthn`). Only challenge, type, UP/UV flags, and P-256 signature are verified.
- **Impact:** If a user’s passkey is used across environments or an attacker induces signing on a malicious RP that shares credential material, on-chain verification may still pass. This is phishing / cross-RP misuse risk for passkey-backed wallets, not a generic Solidity bug, but it is a real authentication weakness in the threat model.

---

## Static signature open relayer when caller unset

- **Location:** `BaseAuth.sol` : `signatureValidation`
- **Mechanism:** For static signatures, if stored `addr == address(0)`, any `msg.sender` may use the static approval until expiry (`timestamp > block.timestamp`).
- **Impact:** If wallet owners set a static approval without binding a relayer address, any bot/attacker can submit that operation first (frontrun), which matters when operation content is time-sensitive or competitive (e.g., liquidations, auctions).

---

### Notes on reviewed areas **not** reported as vulnerabilities

- **`Factory.deploy` permissionless:** Expected for CREATE2 wallet factories; risk is user social-engineering, not contract logic.
- **`selfExecute` without nonce:** Protected by `onlySelf`; inner payload bytes are committed via `keccak256(call.data)` in the signed outer call.
- **`FLAG_ADDRESS` in `BaseSig`:** Does not add signature weight; not an auth bypass by itself.
- **`onlyFallback` / `errorFlag` handling:** Matches documented “only run after immediate predecessor failed” semantics.
- **Main `Calls.execute` nonce ordering:** Correctly uses `decoded.nonce` before validation.

---

### Highest-priority fixes (guidance only; Ask mode)

1. **Guest / Simulator:** Add strict auth, or hard-disable `call`/`delegatecall`/`value` on public entrypoints; simulators should use `eth_call` patterns or static analysis, not live execution.
2. **Estimator:** Use `decoded.nonce`, validate before `_consumeNonce`, restore `_isValidImage`, and avoid mutating execution (use snapshot/staticcall or a dedicated non-production module).
3. **Sessions:** Enforce `call.data.length >= rule.offset + 32` (per rule) in `validatePermission`; disallow duplicate signer nodes or disambiguate by signer+permission set hash.
4. **Passkeys:** Document/enforce off-chain RP isolation; consider on-chain `rpIdHash` binding if threat model requires it.

If you want, I can switch to Agent mode and map each finding to concrete proof-of-concept calldata paths or test cases.

