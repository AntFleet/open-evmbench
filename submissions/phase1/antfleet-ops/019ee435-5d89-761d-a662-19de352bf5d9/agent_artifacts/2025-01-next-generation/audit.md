# Audit: 2025-01-next-generation

## Forwarder signatures are replayable across domains
- Location: `contracts/Forwarder.sol` : `_verifySig` / `execute`
- Mechanism: The forwarder accepts `domainSeparator` as caller-supplied calldata and never checks it against a domain separator owned by this forwarder, chain, or token. `_verifySig` therefore verifies whatever EIP-712 domain the caller provides, as long as the recovered signer matches `req.from`.
- Impact: A signed `ForwardRequest` intended for another forwarder instance, deployment, or chain can be replayed through this forwarder if the request fields and nonce line up. This can move the signer’s EURF on a domain they did not authorize.

## Transfer fees bypass allowance and signed amount limits
- Location: `contracts/Token.sol` : `transferFrom` / `transferWithAuthorization`
- Mechanism: `transferSanity` charges `_payTxFee(sender, amount)` before the normal allowance or signed-transfer execution. `_payTxFee` directly calls `_update(sender, _feesFaucet, txFees)`, so the fee is debited from the token holder without being included in the ERC20 allowance consumed by `transferFrom`, and without being part of the `transferWithAuthorization` signed payload.
- Impact: An approved spender or authorization executor can cause the holder to lose `amount + fee` even though only `amount` was approved or signed. If the fee recipient is attacker-controlled or compromised, this becomes direct extra value extraction; otherwise it is still an unauthorized balance debit beyond the holder’s allowance/signature.

## Revoked controller can still re-enable operations
- Location: `contracts/ERC20ControlerMinterUpgradeable.sol` : `safetySwitch`
- Mechanism: When a controller disables operations, its address is stored in `_operatingController`. While operations are off, `safetySwitch` allows either a default admin or `_operatingController` to turn operations back on, without checking whether `_operatingController` still has the `CONTROLLER` role.
- Impact: If a controller is removed after triggering the safety switch, that removed controller can still re-enable minting and burning. This undermines emergency response and role revocation.

