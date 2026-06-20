# Audit: 2024-03-canto

## Unauthenticated `lzCompose` lets attackers steal router-held tokens
- Location: `contracts/asd/asdRouter.sol` : `lzCompose`
- Mechanism: `lzCompose` never verifies that `msg.sender` is the trusted LayerZero endpoint, so anyone can call it with forged `_from`, `_guid`, and `_message` data. The invalid-payload branch refunds attacker-controlled `amountLD` of attacker-chosen `_from` tokens to attacker-controlled `composeFrom` before even checking the whitelist. The valid-payload path likewise lets a caller redirect already-delivered OFTs through swap/mint/send using attacker-controlled payload fields.
- Impact: An attacker can front-run the real LayerZero compose execution after OFTs are delivered to the router and steal the in-flight bridged tokens, or drain any ERC20 balance stranded in `ASDRouter`.

## Successful compose calls strand excess native tokens
- Location: `contracts/asd/asdRouter.sol` : `_sendASD`
- Mechanism: `lzCompose` is payable and failure paths refund `msg.value`, but successful paths do not. Same-chain sends use none of `msg.value`; cross-chain sends forward only `_payload._feeForSend`; any surplus remains in `ASDRouter`, which has no recovery function.
- Impact: Users or executors who provide native CANTO above the exact consumed fee permanently lose the excess.

## `withdrawCarry` can withdraw backing for bridged-out asD
- Location: `contracts/asd/asdOFT.sol` : `withdrawCarry`
- Mechanism: `ASDOFT` is an OFT, so sending asD off Canto burns local supply while remote OFTs still represent valid global claims on the same Canto-held NOTE backing. `withdrawCarry` computes surplus as `balanceOfUnderlying(address(this)) - totalSupply()`, but `totalSupply()` is only local supply. Bridged-out principal is therefore misclassified as withdrawable carry.
- Impact: The owner, or a compromised owner key, can withdraw collateral needed to redeem asD circulating on other chains, leaving returning holders undercollateralized and unable to redeem 1:1 for NOTE.

