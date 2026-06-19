# Audit: 2025-10-sequence

I found five genuine security issues.

## Cumulative session limits are never persisted
- Location: `src/extensions/sessions/explicit/PermissionValidator.sol` : `validatePermission`
- Mechanism: For cumulative rules, the function computes `usageLimit.usageAmount = value256` in a memory local, but never writes the updated struct back into `newUsageLimits`. Newly initialized usage limits are stored with amount `0`, and existing limits keep their old amount. `_validateLimitUsageIncrement` then requires an `incrementUsageLimit` call using those stale amounts, so storage is not advanced.
- Impact: Any explicit session permission using cumulative parameter rules can be reused beyond its intended limit. A session key limited to a cumulative spend/call amount can repeatedly execute authorized calls because usage remains zero or stale.

## Session signatures replay across wallets
- Location: `src/extensions/sessions/SessionSig.sol` : `hashCallWithReplayProtection`
- Mechanism: The per-call session signature hash includes only `chainId`, `space`, `nonce`, `callIdx`, and `Payload.hashCall(...)`. It does not include the wallet address, `msg.sender`, SessionManager address, or session image hash. `SessionManager.recoverSapientSignature` then validates that signature for whichever wallet called it.
- Impact: A session signature produced for one wallet can be replayed against another wallet with the same session configuration and matching nonce space/nonce. If the second wallet has funds and compatible permissions, an attacker can execute the signed call from that wallet without wallet-specific authorization.

## Public simulation helpers execute real unauthenticated calls
- Location: `src/Simulator.sol` : `simulate`; `src/Guest.sol` : `fallback`
- Mechanism: Both contracts dispatch arbitrary external calls from their own address without authentication. `Simulator.simulate` also permits arbitrary delegatecalls and returns normally, so state changes persist when called in a transaction. `Guest.fallback` similarly performs arbitrary calls encoded in calldata.
- Impact: Any ETH, tokens, or approvals held by these helper contracts can be drained or abused by anyone. A caller can also mutate `Simulator`’s own storage through delegatecall.

## Estimator accepts arbitrary signer configurations and executes real calls
- Location: `src/Estimator.sol` : `_isValidImage`, `estimate`
- Mechanism: `_isValidImage` calls `super._isValidImage(_imageHash)` but ignores the result and always returns `true`. Therefore any attacker can create a signature under an attacker-chosen image hash and pass validation. `estimate` then consumes nonce state and executes the payload calls normally instead of reverting.
- Impact: Anyone can execute arbitrary calls from the Estimator contract. Any ETH, tokens, or approvals held by the Estimator can be stolen or abused.

## Zero-address ECDSA signers are universally forgeable
- Location: `src/modules/auth/BaseSig.sol` : `recoverBranch`; `src/extensions/recovery/Recovery.sol` : `isValidSignature`
- Mechanism: Failed `ecrecover` returns `address(0)`. The normal and `eth_sign` signature branches add weight for the recovered address without rejecting zero. Recovery mode also treats `addr == _signer` as valid, so `_signer == address(0)` accepts any invalid compact signature.
- Impact: Any wallet or recovery configuration that includes `address(0)` as a signer/recovery signer is compromised. Attackers can provide invalid ECDSA bytes and satisfy that signer’s weight or queue recovery payloads as the zero signer.

