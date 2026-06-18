# Audit: 2025-10-sequence

## 1. Nonce consumed before signature validation allows permanent denial of service
- Location: `src/modules/Calls.sol` : `execute` and `src/Estimator.sol` : `estimate`
- Mechanism: `_consumeNonce` is called before `signatureValidation`. If the nonce matches the current nonce, it is incremented unconditionally. An attacker can front-run a legitimate transaction with the same nonce but an invalid signature, causing the nonce to advance. The legitimate transaction will then fail with `BadNonce` because the nonce no longer matches. This can be repeated for every nonce, permanently locking the wallet.
- Impact: An attacker can prevent the wallet from executing any transactions, effectively freezing all funds and operations.

## 2. Estimator completely bypasses signature validation
- Location: `src/Estimator.sol` : `_isValidImage`
- Mechanism: The `_isValidImage` override calls `super._isValidImage(_imageHash)` and discards the result, then unconditionally returns `true`. Therefore any signature is accepted regardless of the actual image hash. The `estimate` function, which executes the payload, will accept any payload with any signature (as long as the nonce is correct).
- Impact: Anyone can execute arbitrary calls on the `Estimator` contract, stealing any funds or assets it holds. While the `Estimator` is not the wallet, if it ever controls value, it is completely drained.

## 3. PermissionValidator permits bypass via short calldata
- Location: `src/extensions/sessions/explicit/PermissionValidator.sol` : `validatePermission`
- Mechanism: The validation extracts a `bytes32` value from the call’s `data` at a user-controlled `rule.offset` using `LibBytes.readBytes32`. This function does not check that the calldata is long enough; reading beyond the calldata length returns zero. An attacker can craft a call with calldata shorter than the `offset`, making the extracted value zero. If the permission rule expects a non-zero value or a specific value, the condition can be satisfied spuriously.
- Impact: A malicious session signer can bypass permission rules that rely on calldata parameters, potentially executing unauthorized operations.

## 4. Simulator and Guest execute arbitrary calls without any access control
- Location: `src/Simulator.sol` : `simulate`, `src/Guest.sol` : `fallback`
- Mechanism: Both `Simulator.simulate` and `Guest`’s fallback function accept external calls and execute them without any signature or nonce checks. They are meant as helpers, but they are not `view` and will permanently modify the contract’s state. If these contracts hold any ETH or tokens, they can be stolen.
- Impact: Any funds sent to these contracts are immediately at risk of being drained by anyone.

## 5. Missing delegatecall check in session increment call validation
- Location: `src/extensions/sessions/SessionManager.sol` : `_validateLimitUsageIncrement` and `_validateExplicitCall`
- Mechanism: The first call of a session payload is expected to be a `call` to the `SessionManager`’s `incrementUsageLimit`. The validation verifies the target and data, but does not check `call.delegateCall`. If the call is a `delegatecall`, the `incrementUsageLimit` logic executes in the wallet’s context with `msg.sender` being the original transaction sender, not the wallet. This can cause the session limits to be updated for the wrong address, potentially allowing usage limits to be circumvented or causing unexpected reverts.
- Impact: A malicious payload could use a `delegatecall` to the `SessionManager`, disrupting the session limit tracking and potentially bypassing spending limits.
