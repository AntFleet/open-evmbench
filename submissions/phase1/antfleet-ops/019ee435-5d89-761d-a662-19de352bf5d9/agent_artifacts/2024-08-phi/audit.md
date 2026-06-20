# Audit: 2024-08-phi

## Claims can be replayed for arbitrary quantity
- Location: `src/PhiFactory.sol` : `signatureClaim`, `merkleClaim`, `_validateAndUpdateClaimState`
- Mechanism: Claim state is only written, never enforced: `artMinted` and `credMinted` are set but not checked. Also, `quantity` is not part of the signed payload or Merkle leaf, so a valid claim authorization can be submitted repeatedly or with a larger quantity.
- Impact: Any eligible claimant, or anyone holding a valid proof/signature, can mint up to the full remaining `maxSupply`, exhausting the art supply and preventing other eligible users from claiming.

## Art creation signatures can be hijacked or replayed
- Location: `src/PhiFactory.sol` : `createArt`, `_validateArtCreationSignature`, `_createERC1155Data`
- Mechanism: The signed art creation payload only covers `(expiresIn, uri, credData)`. It does not bind `msg.sender`, `artist`, `receiver`, `maxSupply`, `mintFee`, schedule, `soulBounded`, `artId`, or a nonce. Any user who obtains a valid signed payload can choose their own `CreateConfig`, front-run the intended creator, and replay the same signature until expiry.
- Impact: An attacker can create art under someone else’s signed cred data while making themselves the artist/receiver, choosing malicious mint economics, or creating duplicate/replayed art entries.

## Global Merkle root can be overwritten across existing art
- Location: `src/PhiFactory.sol` : `_initializePhiArt`, `merkleClaim`
- Mechanism: Merkle roots are stored globally by `(credChainId, credId)` in `credMerkleRoot`, not per `artId`. Creating any later art for the same cred overwrites the root used by all prior Merkle-verified art claims.
- Impact: A later art creation can invalidate existing allowlists or replace them with a different root, enabling unauthorized claims or permanently blocking legitimate Merkle claimants for previously created art.

## Signature claims bypass the art verification type
- Location: `src/PhiFactory.sol` : `signatureClaim`
- Mechanism: `merkleClaim` verifies that `art.verificationType == "MERKLE"`, but `signatureClaim` does not verify that the art uses `"SIGNATURE"` verification. Direct calls to `signatureClaim` can therefore be made for Merkle-gated art if a Phi signer signature exists for that `artId`.
- Impact: Merkle-only art can be claimed through the signature path, bypassing the intended Merkle eligibility gate.

## Factory-held ETH can subsidize attacker claims
- Location: `src/PhiFactory.sol` : `claim`
- Mechanism: `claim` computes the required mint fee and calls `this.merkleClaim` or `this.signatureClaim` with exactly that amount, but it never checks that the caller supplied that amount in `msg.value`. If the factory has any ETH balance, the internal self-call can spend factory-held ETH instead of caller-provided ETH.
- Impact: An attacker can claim NFTs using ETH accidentally or forcibly held by the factory, effectively draining stuck factory funds into protocol/reward payments for the attacker’s mint.

## Anyone can grief-lock another curator’s shares
- Location: `src/Cred.sol` : `buyShareCredFor`, `_handleTrade`
- Mechanism: `buyShareCredFor` allows any caller to buy shares for any `curator_`. `_handleTrade` then updates `lastTradeTimestamp[credId][curator_]`, and sells are blocked for the whole curator position until `SHARE_LOCK_PERIOD` passes.
- Impact: An attacker can repeatedly buy small amounts for a victim to keep resetting their sell lock, preventing the victim from exiting their position during market movement.

## Public position-list mutators can corrupt curator accounting
- Location: `src/Cred.sol` : `_addCredIdPerAddress`, `_removeCredIdPerAddress`
- Mechanism: These functions are declared `public` even though they mutate internal position-indexing state. Any caller can add fake cred IDs or remove real cred IDs from any curator’s `_credIdsPerAddress` list without changing the actual share balance.
- Impact: An attacker can corrupt a victim’s position index so that future full sells revert when `_updateCuratorShareBalance` tries to remove the cred ID, effectively locking the victim’s remaining shares unless the index state is repaired.

## Reentrant cred creation can corrupt cred IDs
- Location: `src/Cred.sol` : `_createCredInternal`, `_handleTrade`
- Mechanism: `_createCredInternal` initializes `creds[credIdCounter]` and then calls `buyShareCred` before incrementing `credIdCounter`. During the initial buy, `_handleTrade` can refund ETH to the creator before the counter is incremented. A malicious creator contract can reenter `createCred` during that refund and create another cred using the same `credIdCounter`.
- Impact: An attacker can overwrite the in-progress cred, desynchronize emitted IDs and returned IDs, skip counters, and create malformed or phantom credential state.

