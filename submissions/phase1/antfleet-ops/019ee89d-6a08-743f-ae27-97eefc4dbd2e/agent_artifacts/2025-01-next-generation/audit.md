# Audit: 2025-01-next-generation

## Unrestricted mint/burn via `forceTransfer` with a zero `from`/`to`
- Location: contracts/ERC20AdminUpgradeable.sol : `forceTransfer` (and `adminSanity`)
- Mechanism: `forceTransfer` is ADMIN-gated and calls `_update(from, to, amount)` directly. OpenZeppelin's `_update` treats `from == address(0)` as a **mint** (it increments `totalSupply`) and `to == address(0)` as a **burn**. The pre-flight `adminSanity(from, to)` validates only the recipient (`isBlacklisted(to)`, `to != address(this)`) and never inspects `from`, and `forceTransfer` performs none of the minting safeguards — no `MASTER_MINTER`/`MINTER_ROLE` check, no `minterAllowed` decrement, no `_operating` (safetySwitch) check. An ADMIN can therefore call `forceTransfer(address(0), attacker, amount)` to mint arbitrary supply, or `forceTransfer(victim, address(0), amount)` to destroy any holder's balance, entirely outside the minter authorization system.
- Impact: The ADMIN role (scoped to pause/blacklist/forced-transfer) can mint unlimited EURF — even while the `safetySwitch` has disabled the official minting path — and burn any user's tokens, escalating beyond its intended authority and nullifying the minter-allowance and emergency-stop controls.

## Forwarder accepts an unvalidated domain separator → cross-chain signature replay
- Location: contracts/Forwarder.sol : `_verifySig` (reached via `execute` / `verify`)
- Mechanism: `execute` and `verify` take `domainSeparator` and `requestTypeHash` as caller-supplied calldata and forward them to `_verifySig`, which constructs the EIP-712 digest using the supplied `domainSeparator` verbatim. The only validation is `require(typeHashes[requestTypeHash])`; there is **no `domains[domainSeparator]` registry check** (the OpenGSN-style domain registration was dropped), so the forwarder never binds a request to its own `chainId`/contract address. The sole replay guard is the per-`from` sequential `nonces` mapping, which is independent for every deployment. A `ForwardRequest` a holder legitimately signed for one EURF forwarder/chain can thus be re-presented to another EURF forwarder deployment by any relayer that re-supplies the original `domainSeparator`, provided the holder's nonce there matches.
- Impact: A relayer can replay a holder's signed gasless `transfer` against another chain/forwarder deployment, forcing an unintended duplicate EURF transfer out of the holder's balance without any new authorization.

## Unprotected initializers allow ownership hijack on non-atomic deployment
- Location: contracts/Token.sol : `initialize` and contracts/Forwarder.sol : `initialize`
- Mechanism: Both `initialize` functions are externally callable, guarded only by `initializer`, and assign control to `msg.sender` (`_grantRole(OWNER, msg.sender)` / `__Ownable_init(_msgSender())`) with no binding to the intended deployer. If the proxy is deployed and initialized in separate transactions, an attacker can front-run the legitimate `initialize` call, becoming OWNER. Because `EURFToken` is UUPS with `_authorizeUpgrade` gated solely on `OWNER`, the attacker can then upgrade the implementation to arbitrary code.
- Impact: With a non-atomic deployment, an attacker seizes the OWNER role and can upgrade the proxy to a malicious implementation, taking full control of token supply and balances.

