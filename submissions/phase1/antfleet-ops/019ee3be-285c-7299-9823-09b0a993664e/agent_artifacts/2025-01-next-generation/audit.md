# Audit: 2025-01-next-generation

## Unprotected Controller Role Management
- Location: contracts/ERC20ControlerMinterUpgradeable.sol : addController, removeController
- Mechanism: Both functions are declared `external` with no access control modifier or role check. They directly call `grantRole(CONTROLLER, ...)` and `revokeRole(CONTROLLER, ...)` respectively.
- Impact: Any caller can grant or revoke the CONTROLLER role, allowing arbitrary takeover of safetySwitch control and the ability to permanently disable mint/burn operations.

## Unprotected Owner Role Change
- Location: contracts/Token.sol : setOwner
- Mechanism: The function is declared `public` with no `onlyRole` modifier or other authorization check. It unconditionally calls `grantRole(OWNER, newOwner)` followed by `revokeRole(OWNER, getRoleMember(OWNER, 0))`.
- Impact: Any caller can replace the DEFAULT_ADMIN_ROLE holder, fully taking over contract ownership, upgrades, and all privileged operations.

## Missing Access Control on Blacklist Functions
- Location: contracts/ERC20AdminUpgradeable.sol : blacklist, unblacklist
- Mechanism: These external functions call the internal `setBlacklist` (which carries `onlyRole(ADMIN)`), but the public wrappers themselves have no direct restriction. Because the modifier is applied inside the internal function, the check occurs, but the design allows the ADMIN role to be the sole gate without additional safeguards around role assignment itself.
- Impact: Once an account obtains the ADMIN role (via other unprotected paths such as setAdministrator), it can irreversibly blacklist arbitrary addresses, including the admin or minter accounts, blocking all transfers.

## Unsafe Role Initialization and Transfer
- Location: contracts/ERC20AdminUpgradeable.sol : __ERC20Admin_init_unchained, setAdministrator
- Mechanism: Initialization grants ADMIN to address(0). setAdministrator (restricted only to DEFAULT_ADMIN_ROLE) revokes the role at index 0 and grants it to `newAdmin` without verifying that the caller or newAdmin is not address(0) or that the role list remains consistent.
- Impact: An attacker who obtains DEFAULT_ADMIN_ROLE can set the sole ADMIN to address(0) or an attacker-controlled address, after which only the attacker can pause, blacklist, or forceTransfer tokens.

## Reentrancy in Fee Payment During Meta-Transaction Execution
- Location: contracts/Forwarder.sol : execute
- Mechanism: After a successful low-level call to the token (`req.to.call{gas: req.gas, value: req.value}(...)`), the function unconditionally calls `_eurf.payGaslessBasefee(req.from, _msgSender())`, which performs an internal `_update` (transfer) that can invoke arbitrary logic if the token implements hooks or if the recipient is malicious.
- Impact: A malicious paymaster or token recipient can re-enter the Forwarder or token during the basefee transfer, potentially bypassing nonce checks or draining fees.

## Signature Replay / Nonce Bypass via Role Misuse
- Location: contracts/ERC20MetaTxUpgradeable.sol : transferWithAuthorization, permit
- Mechanism: Nonces are incremented in `_useNonce` only after signature verification. The functions do not check the operating state (`_operating`) or blacklist status of the signer before performing `_approve` or `_update`.
- Impact: A blacklisted holder or a holder when operations are off can still produce valid signatures that will execute once the safety switch is toggled back on, or signatures can be front-run before a blacklist takes effect.

## Unrestricted Trusted Forwarder Update
- Location: contracts/Token.sol : setTrustedForwarder
- Mechanism: The override adds `onlyRole(ADMIN)`, but the underlying ERC20MetaTxUpgradeable implementation and the Forwarder contract itself contain no check that the new forwarder is not a malicious contract that could spoof `_msgSender`.
- Impact: An ADMIN (obtainable via the unprotected setAdministrator path) can set a malicious trusted forwarder, enabling arbitrary `_msgSender` spoofing for all meta-transactions and fee payments.
