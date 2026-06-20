# Audit: 2025-01-next-generation

 ## Shared nonce across permit and transferWithAuthorization
- Location: `contracts/ERC20MetaTxUpgradeable.sol` : `_useNonce`, `permit`, `transferWithAuthorization`
- Mechanism: Both `permit` and `transferWithAuthorization` consume nonces from the same `_nonces[owner]` counter even though they are independent authorization mechanisms with different type-hashes. A valid signature of one type will increment the counter and therefore invalidate any concurrent valid signature of the other type that happens to use the same nonce.
- Impact: An attacker or a benign relayer can front-run a user’s signed `permit` or `TransferWithAuthorization` with the other type using the same nonce, causing the legitimate signature to revert and denying service for meta-transactions or approvals.

## Fee enforced but not collected when fee faucet is zero
- Location: `contracts/Token.sol` : `_payTxFee`; `contracts/FeesHandlerUpgradeable.sol` : `setFeeFaucet`
- Mechanism: `_payTxFee` unconditionally requires `balanceOf(from) >= txFees + txAmount`, but the actual fee transfer (`_update(from, _feesFaucet, txFees)`) is skipped when `_feesFaucet == address(0)` and `setFeeFaucet` has no zero-address check. If the faucet is unset or set to zero, senders must still hold enough balance for a fee that is never moved to any recipient.
- Impact: Users with balances between the transfer amount and `amount + fee` cannot move their tokens even though no fee is collected, effectively freezing part of user funds and creating a protocol-wide denial-of-service condition.

## Missing zero-address validation in privileged setters
- Location: `contracts/ERC20AdminUpgradeable.sol` : `setAdministrator`; `contracts/ERC20ControlerMinterUpgradeable.sol` : `setMasterMinter`; `contracts/FeesHandlerUpgradeable.sol` : `setFeeFaucet`
- Mechanism: `setAdministrator`, `setMasterMinter`, and `setFeeFaucet` all accept `address(0)`. Granting `ADMIN` or `MASTER_MINTER` to the zero address makes those roles unusable, and setting the fee faucet to zero triggers the fee-without-collection bug.
- Impact: An accidental or malicious privileged call can permanently disable admin/minter capabilities or freeze user funds by leaving the fee faucet at zero while a positive fee rate is still enforced.

## Removed controller can re-enable minting/burning
- Location: `contracts/ERC20ControlerMinterUpgradeable.sol` : `safetySwitch`
- Mechanism: When a controller turns operations off, `_operatingController` is stored. The branch that turns operations back on only verifies `hasRole(DEFAULT_ADMIN_ROLE, ...)` or `_operatingController == _msgSender()`; it never checks that the caller still holds the `CONTROLLER` role, and `removeController` does not clear `_operatingController`.
- Impact: A controller whose role has been revoked can still call `safetySwitch()` to turn minting and burning back on, bypassing the owner’s revocation.

## Meta-transaction fees are not authorized by the signer
- Location: `contracts/Forwarder.sol` : `execute`; `contracts/Token.sol` : `payGaslessBasefee`, `transferSanity`
- Mechanism: The `ForwardRequest` signed by `req.from` covers only `to`, `value`, `gas`, `nonce`, and `data`. After executing the signed transfer, the Forwarder unilaterally calls `payGaslessBasefee(req.from, relayer)`, and the token’s `transfer` also charges a transaction fee whose rate is controlled by `ADMIN`. Neither fee amount is part of the signed payload.
- Impact: Signers have no on-chain control over the fees charged for a meta-transaction; a malicious admin or relayer can drain a signer’s balance by raising `_gaslessBasefee` or `_txfeeRate` before executing a previously signed request.

## Pause/blacklist do not cover mint, burn, forceTransfer, or fee transfers
- Location: `contracts/ERC20ControlerMinterUpgradeable.sol` : `mint`, `burn`; `contracts/ERC20AdminUpgradeable.sol` : `forceTransfer`; `contracts/Token.sol` : `_payTxFee`
- Mechanism: `adminSanity`—which enforces pause, blacklist, and the prohibition on transfers to the contract itself—is applied only in the overridden `transfer`, `transferFrom`, and `transferWithAuthorization` paths. `mint`, `burn`, `forceTransfer`, and the internal `_payTxFee` call `_update` directly without invoking `adminSanity`.
- Impact: When the contract is paused or an address is blacklisted, minters and admins can still issue, destroy, or seize tokens, and fee payments can still be directed to a blacklisted fee faucet, undermining the intended pause/blacklist protections.

## Forwarder accepts arbitrary EIP-712 domain separators
- Location: `contracts/Forwarder.sol` : `verify`, `execute`, `_verifySig`
- Mechanism: The forwarder receives a `domainSeparator` from the caller and only checks that the provided signature matches that separator. It never validates the separator against `_eurf.DOMAIN_SEPARATOR()` or any other current on-chain value.
- Impact: Signatures signed for a previous domain separator (for example, after an upgrade that changes the EIP-712 domain) or for a different domain can be replayed through this forwarder, potentially executing stale or unintended meta-transactions.

## Initial ADMIN and MASTER_MINTER roles granted to address(0)
- Location: `contracts/ERC20AdminUpgradeable.sol` : `__ERC20Admin_init_unchained`; `contracts/ERC20ControlerMinterUpgradeable.sol` : `__ERC20ControlerMinter_init_unchained`
- Mechanism: The initializer grants `ADMIN` and `MASTER_MINTER` to `address(0)`. Since zero cannot call contracts, `pause`, `blacklist`, fee settings, and minter management are inoperative until the owner explicitly calls `setAdministrator`/`setMasterMinter`.
- Impact: If the owner fails to assign real addresses after deployment, the contract is left without admin or minter capabilities—unpausable, unblacklistable, and unmintable—creating a permanent governance lockout.

## Ownership transfer does not revoke other privileged roles from the old owner
- Location: `contracts/Token.sol` : `setOwner`
- Mechanism: `setOwner` grants `OWNER`/`DEFAULT_ADMIN_ROLE` to the new owner and revokes it from the address returned by `owner()`, but it does not revoke any `ADMIN`, `MASTER_MINTER`, or `MINTER_ROLE` the old owner may also hold.
- Impact: A previous owner can retain operational control—such as blacklisting users, minting tokens, or changing fees—after ownership has been transferred, violating the expectation that ownership transfer relinquishes all authority.
