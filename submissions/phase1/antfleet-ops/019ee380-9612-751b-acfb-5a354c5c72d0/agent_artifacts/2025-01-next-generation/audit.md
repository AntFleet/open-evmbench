# Audit: 2025-01-next-generation

Below are the genuine security vulnerabilities I found in this codebase.

## Meta-transaction fee is read from mutable admin state and is not bound by the signer's authorization
- Location: `Token.sol` : `payGaslessBasefee` / `_payTxFee` (and `Forwarder.sol` : `execute`)
- Mechanism: A user signs a `ForwardRequest` whose signed payload is only `(from, to, value, gas, nonce, data)`. Neither the transfer fee (`_txfeeRate`) nor `_gaslessBasefee` is part of the signed data. At execution time, `Forwarder.execute` first runs the forwarded `transfer` (which charges `calculateTxFee` via `transferSanity`) and then calls `_eurf.payGaslessBasefee(req.from, msg.sender)`, which reads `_gaslessBasefee` live from storage and `_update(payer, paymaster, _gaslessBasefee)`. Because the deducted amount is whatever the current admin-set value is, and the only guard is `balanceOf(payer) >= _gaslessBasefee`, the amount actually taken from the signer is unbounded and unauthorized by the signature.
- Impact: A relayer/paymaster colluding with (or front-running a fee change by) the admin can drain up to the signer's entire balance for a request the signer believed authorized only a small transfer. The signer has no on-chain cap protecting them between signing and execution.

## Forwarder signatures are not bound to the contract/chain (caller-supplied `domainSeparator`) — cross-deployment replay
- Location: `Forwarder.sol` : `_verifySig` / `execute`
- Mechanism: `_verifySig` builds the EIP-712 digest as `keccak256("\x19\x01" || domainSeparator || keccak256(_getEncoded(req, requestTypeHash, suffixData)))`, where both `domainSeparator` and `requestTypeHash` are **parameters supplied by the caller** and are never compared against a domain separator the contract computes for itself (chainid/verifyingContract). The contract only verifies `recover(sig) == req.from`. Unlike `permit`/`transferWithAuthorization` (which use `_hashTypedDataV4` and are therefore chain-bound), the forwarder trusts whatever domain the relayer passes.
- Impact: A valid `(req, sig)` collected for one Forwarder deployment can be replayed on any other deployment of the same Forwarder (e.g., the same token/forwarder bridged or redeployed on another chain) as long as `nonces[req.from]` matches. Since nonces start at 0, a user's first signed gasless transfer is replayable across chains, causing an unintended second transfer.

## `adminSanity` checks the caller's role, not the token sender, to bypass pause/blacklist
- Location: `ERC20AdminUpgradeable.sol` : `adminSanity` (reached from `Token.transferFrom` / `transferWithAuthorization`)
- Mechanism: `adminSanity(from, to)` gates the pause and sender-blacklist checks behind `if (!hasRole(ADMIN, _msgSender()))`. `_msgSender()` is the transaction caller, which equals the token sender only in `transfer`. In `transferFrom` (and `transferWithAuthorization`) the caller/spender is a different party than `from`/`holder`. So when an ADMIN is the caller, the `paused()` and `isBlacklisted(from)` checks are skipped for an arbitrary `from` account.
- Impact: An ADMIN can execute `transferFrom` on behalf of any account that has granted an allowance even while the contract is paused, and can move tokens out of a blacklisted sender (sender-blacklist check skipped), defeating the pause/freeze controls for allowance- and authorization-based flows.

## `transferFrom` charges the fee from the owner beyond the approved allowance
- Location: `Token.sol` : `transferFrom` → `transferSanity` → `_payTxFee`
- Mechanism: `transferSanity(sender, recipient, amount)` calls `_payTxFee(sender, amount)`, which moves `calculateTxFee(amount)` from `sender` to the fee faucet, requiring `balanceOf(sender) >= fee + amount`. Then `super.transferFrom` spends allowance only for `amount` via `_spendAllowance(sender, msgSender, amount)`. The fee is taken directly from the owner's balance and is never accounted against the spender's allowance.
- Impact: An approved spender causes the owner to lose `amount + fee` while the owner only approved `amount`. The allowance no longer represents the maximum debit the owner can incur, breaking the ERC-20 allowance guarantee (the extra is siphoned to the fee faucet on every `transferFrom`).

## Unprotected proxy `initialize()` enables initialization front-running and full takeover
- Location: `Token.sol` : `initialize`
- Mechanism: `initialize()` is `public initializer` with no access restriction and grants `OWNER` (`DEFAULT_ADMIN_ROLE`) to `msg.sender`. The implementation constructor locks the logic contract (`constructor() initializer {}`), but the proxy itself must be initialized in a separate transaction. If proxy deployment and `initialize()` are not performed atomically, any observer can call `initialize()` first.
- Impact: The front-runner becomes `OWNER`, gaining `_authorizeUpgrade` rights (UUPS) and the ability to set administrators, master minter, etc. — i.e., complete control over the token, including upgrading to arbitrary logic to drain all funds.

## `mint` bypasses pause and recipient-blacklist (no `_update` override)
- Location: `ERC20ControlerMinterUpgradeable.sol` : `mint` (and `burn`)
- Mechanism: All compliance checks (pause, blacklist, `to == address(this)`) live in the public wrappers `transfer`/`transferFrom`/`transferWithAuthorization`/`forceTransfer`, not in `_update`, which is not overridden. `mint` calls `_mint` → `_update(0, to, amount)` directly with no `adminSanity`. There is no `whenNotPaused` and no `isBlacklisted(to)` check.
- Impact: A minter can mint tokens to a blacklisted address and can mint even while the contract is paused, undermining the freeze/compliance guarantees the pause and blacklist mechanisms are meant to provide for a regulated stablecoin.

