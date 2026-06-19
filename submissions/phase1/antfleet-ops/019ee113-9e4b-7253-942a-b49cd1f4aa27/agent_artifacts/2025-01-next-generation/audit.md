# Audit: 2025-01-next-generation

## Missing Access Control on Critical Role Management Functions

- **Location:** `contracts/ERC20ControlerMinterUpgradeable.sol` : `setMasterMinter`, `addMinter`, `removeMinter`, `addController`, `removeController`
- **Mechanism:** Multiple role-management functions are declared `external`/`public` without any `onlyRole` or other access-control modifier. `setMasterMinter` unconditionally revokes the current master minter and grants the role to an arbitrary address; `addMinter`/`removeMinter` arbitrarily set/clear `MINTER_ROLE` and `minterAllowed`; `addController`/`removeController` arbitrarily grant/revoke the `CONTROLLER` role.
- **Impact:** Any external caller can become the master minter (with effectively unlimited mint authority since the master minter bypasses the `minterAllowed` check in `mint`), add themselves as a minter with any allowance, or become a controller and trigger `safetySwitch()` to halt minting/burning operations permanently (re-enabling requires either DEFAULT_ADMIN_ROLE or the controller who paused it).

## Unprotected Owner Transfer

- **Location:** `contracts/Token.sol` : `setOwner`
- **Mechanism:** `setOwner` is declared `public` with no access-control modifier. It calls `grantRole(OWNER, newOwner)` followed by `revokeRole(OWNER, getRoleMember(OWNER, 0))`, allowing any caller to transfer the DEFAULT_ADMIN_ROLE.
- **Impact:** A trivial front-run or direct call lets an attacker seize full administrative control of the contract — including the ability to authorize upgrades (`_authorizeUpgrade`), pause/unpause, blacklist, mint, and ultimately drain the contract.

## `mint` Bypasses Recipient Blacklist

- **Location:** `contracts/Token.sol` : `mint` / `ERC20ControlerMinterUpgradeable.sol` : `mint`
- **Mechanism:** `mint` calls `_mint(to, amount)` directly without invoking `adminSanity`. Unlike `transfer`/`transferFrom`/`transferWithAuthorization`, there is no check that `to` is not blacklisted. Note that `adminSanity` always enforces `RecipientBlacklistedError` even for ADMIN callers, so this is an inconsistency rather than an intentional ADMIN bypass.
- **Impact:** Blacklisted addresses (e.g., sanctioned or compromised addresses) can still receive freshly minted tokens, undermining the purpose of the blacklist. This creates an unintended backdoor that defeats the compliance/control mechanism.

## Trusted Forwarder Can Arbitrarily Debit Any Holder

- **Location:** `contracts/Token.sol` : `payGaslessBasefee`
- **Mechanism:** `payGaslessBasefee` only verifies that `msg.sender` is the trusted forwarder; it performs no signature or nonce check on the `payer` parameter. The forwarder's `execute` function does verify signatures, but a compromised or malicious trusted forwarder (or one whose owner acts maliciously) can call `payGaslessBasefee` directly with any holder's address to extract tokens up to `_gaslessBasefee` per call.
- **Impact:** If the forwarder is compromised, an attacker can repeatedly call `payGaslessBasefee` against arbitrary holders and collect the base fee each time. The ADMIN-controlled `setTrustedForwarder` is the sole gatekeeper.

## `setGaslessBasefee` Lacks Effective Upper-Bound Validation

- **Location:** `contracts/FeesHandlerUpgradeable.sol` : `setGaslessBasefee`
- **Mechanism:** The guard is `if (newGaslessBasefee < 0) revert NegativeBasefee()`. Because `newGaslessBasefee` is a `uint256`, this condition is unreachable and no maximum is enforced.
- **Impact:** An ADMIN (or, in this contract, anyone if the override is missing) can set `_gaslessBasefee` to `type(uint256).max`, effectively bricking all gasless meta-transactions because no holder will ever have sufficient balance to satisfy the `payGaslessBasefee` balance check.

## `_payTxFee` Emits Misleading Event When Faucet Is Zero

- **Location:** `contracts/Token.sol` : `_payTxFee`
- **Mechanism:** The function always emits `FeesPaid(from, txFees)` and returns success even when `_feesFaucet == address(0)` and no actual token movement occurred. The fee is computed and the balance check is performed, but no value is transferred.
- **Impact:** Off-chain indexers and accounting systems that rely on `FeesPaid` to track collected fees will over-report. This is an accounting/integrity issue rather than a direct loss of funds.

## `setBlacklist` Access Control Is Fragile Due to `internal` Visibility

- **Location:** `contracts/ERC20AdminUpgradeable.sol` : `setBlacklist`, `blacklist`, `unblacklist`
- **Mechanism:** The role-restricted function `setBlacklist` is declared `internal` with `onlyRole(ADMIN)`, while the public entry points `blacklist`/`unblacklist` have no modifiers themselves and rely on the inner modifier to enforce access control. The modifier does correctly check `_msgSender()` of the original caller, but the pattern is fragile: any future inheriting contract that wraps or re-exposes `setBlacklist` without preserving the ADMIN check would silently bypass authorization.
- **Impact:** Currently functioning, but the design relies on every wrapper correctly preserving `_msgSender()` semantics. Combined with the meta-tx `_msgSender` override, any wrapper that fails to propagate context correctly could allow unauthorized blacklisting or unblacklisting.

## Forwarder Domain Separator Is Caller-Provided and Unvalidated

- **Location:** `contracts/Forwarder.sol` : `verify`, `execute`
- **Mechanism:** Both functions accept `domainSeparator` as an external parameter and use it directly when constructing the EIP-712 digest. There is no check that the provided separator matches the token's actual `DOMAIN_SEPARATOR()` (e.g., `EURFToken.DOMAIN_SEPARATOR()`).
- **Impact:** A caller can supply a different domain separator when verifying signatures. While the signer must have signed the digest with the supplied separator, this allows signature malleability across domain contexts and breaks the invariant that signatures are bound to the specific token contract. If a token is deployed with a different name or upgraded, previously valid meta-txs could be replayed against a differently-configured domain.

## Missing Zero-Address and Input Validation in Role Setters

- **Location:** `contracts/ERC20ControlerMinterUpgradeable.sol` : `addController`, `addMinter`, `setMasterMinter`; `contracts/FeesHandlerUpgradeable.sol` : `setFeeFaucet`
- **Mechanism:** `addController` and `addMinter` do not reject `address(0)`. `setFeeFaucet` accepts `address(0)` (intentional to disable fees) but does not emit a distinct event to signal the disabled state, and `setMasterMinter` accepts `address(0)` as the new master minter, which permanently disables all minter management (no one can update allowances afterward).
- **Impact:** Operational footguns: an accidental zero-address input to `setMasterMinter` or `addMinter` can permanently disable minting or remove all controllers, locking the contract into an inoperable state.

## `setMasterMinter` Emits Spurious Allowance Event

- **Location:** `contracts/ERC20ControlerMinterUpgradeable.sol` : `setMasterMinter`
- **Mechanism:** Emits `MinterAllowanceUpdated(newMasterMinter, type(uint256).max)` but never writes to `minterAllowed[newMasterMinter]`. The master minter bypasses the allowance check entirely in `mint`.
- **Impact:** Off-chain systems that read `MinterAllowanceUpdated` to track per-minter allowances will record an incorrect value of `type(uint256).max` that does not correspond to any on-chain state, leading to flawed accounting.

## `updateMintingAllowance` Does Not Emit Old Value for Auditability

- **Location:** `contracts/ERC20ControlerMinterUpgradeable.sol` : `updateMintingAllowance`
- **Mechanism:** Only the new allowance is emitted via `MinterAllowanceUpdated`. The previous value is not included.
- **Impact:** Minor — complicates off-chain auditing of allowance changes and can mask accidental or malicious allowance increases.
