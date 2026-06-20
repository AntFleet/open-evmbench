# Audit: 2025-01-next-generation

## Caller-supplied EIP-712 domain enables signature replay
- Location: `Forwarder.sol` : `execute`
- Mechanism: `_verifySig` accepts `domainSeparator` as an untrusted calldata argument and never checks it against a domain owned by this forwarder, this chain, or this token. The digest is therefore computed over whatever EIP-712 domain the caller supplies, while the nonce is local to this forwarder.
- Impact: A signature over the same `ForwardRequest` type from another forwarder/domain can be replayed here if the local nonce matches, executing an EURF `transfer` the signer did not authorize for this forwarder.

## Delegated transfers debit fees outside the approved or signed amount
- Location: `Token.sol` : `transferFrom`, `transferWithAuthorization`
- Mechanism: `transferSanity` calls `_payTxFee(sender, amount)` before the actual delegated transfer. For `transferFrom`, allowance is later spent only for `amount`, not `amount + txFee`. For `transferWithAuthorization`, the signed struct authorizes only `value`, but execution debits `value + calculateTxFee(value)`.
- Impact: A spender or relayer with limited authorization can make the holder lose more tokens than the allowance or signature amount covers, with the excess paid to `_feesFaucet`. Stale signed authorizations are especially exposed if fees change before execution.

## Gasless fee payments bypass blacklist recipient checks
- Location: `Token.sol` : `payGaslessBasefee`
- Mechanism: `payGaslessBasefee` only checks that `msg.sender` is the trusted forwarder, then transfers `_gaslessBasefee` with `_update(payer, paymaster, ...)`. It does not call `adminSanity`, so it does not reject a blacklisted `paymaster`.
- Impact: A blacklisted address can still receive EURF by executing a victim’s valid forwarded transfer and collecting the gasless base fee, bypassing the token’s normal recipient blacklist enforcement.

## Former master minter can retain minting power after rotation
- Location: `ERC20ControlerMinterUpgradeable.sol` : `setMasterMinter`
- Mechanism: `setMasterMinter` revokes only `MASTER_MINTER` from the former account and merely emits `MinterAllowanceUpdated(formerMasterMinter, 0)`. It does not clear `minterAllowed[formerMasterMinter]` or revoke `MINTER_ROLE`. A current master minter can grant itself `MINTER_ROLE` with a large allowance before being replaced.
- Impact: After an owner rotates away a compromised or malicious master minter, that former master can continue minting as a regular minter up to its retained allowance.

