# Audit: 2024-08-phi

## Cross-chain replay in signature claims
- Location: src/PhiFactory.sol : signatureClaim
- Mechanism: signatureClaim decodes a chain ID from encodeData_ but discards it and never checks it against block.chainid. Direct calls to PhiFactory.signatureClaim therefore bypass the safer Claimable path that repacks claim data with the current chain ID.
- Impact: A signature issued for one chain can be replayed on another chain with matching signer/art IDs, allowing unauthorized NFT claims and reward routing.

## Art creation signatures can be front-run with attacker-controlled config
- Location: src/PhiFactory.sol : createArt
- Mechanism: _validateArtCreationSignature only verifies signedData_ = (expiresIn, uri, credData). The separate CreateConfig fields, including artist, receiver, maxSupply, mintFee, startTime, endTime, and soulBounded, are not signed, and the signature is not bound to msg.sender or a nonce.
- Impact: Anyone who sees a valid createArt signature can front-run or replay it with themselves as artist/receiver, stealing future rewards/royalties and controlling the art settings.

## createCred reentrancy can overwrite a pending cred and drain ETH
- Location: src/Cred.sol : createCred / _createCredInternal / _handleTrade
- Mechanism: _createCredInternal writes creds[credIdCounter] and then calls buyShareCred before incrementing credIdCounter. The buy path refunds excess ETH before any reentrancy guard and before the creation finishes. A malicious refund receiver can reenter createCred while the same credIdCounter is still active, overwrite the cred’s bonding curve, and then sell shares priced by the new curve.
- Impact: With multiple whitelisted curves, an attacker can buy shares cheaply, overwrite the cred to a more expensive curve, and sell against the contract reserve to drain ETH.

## Factory claim wrapper can spend existing factory ETH
- Location: src/PhiFactory.sol : claim / batchClaim
- Mechanism: claim computes mintFee and calls this.merkleClaim{value: mintFee} or this.signatureClaim{value: mintFee} without checking that the outer caller supplied that amount. The self-call can use ETH already held by PhiFactory, including excess ETH refunded back to PhiFactory during createArt.
- Impact: Attackers can mint with underpayment or zero payment whenever PhiFactory has a balance, draining stuck ETH to subsidize their claims and rewards.

## Claim state is recorded but never enforced
- Location: src/PhiFactory.sol : _validateAndUpdateClaimState
- Mechanism: The function sets artMinted[artId][minter] and credMinted[chainId][credId][minter] to true, but never checks whether either flag was already true.
- Impact: The same eligible minter can claim the same art repeatedly until maxSupply is exhausted, draining supply and repeatedly triggering reward accounting.

## Claim quantity is not authorized
- Location: src/PhiFactory.sol : signatureClaim / merkleClaim
- Mechanism: For signature claims, the signed encodeData_ excludes mintArgs_.quantity. For Merkle claims, the verified leaf is based on minter_ and leafPart_, while quantity is caller-supplied. The contract only checks quantity > 0 and remaining maxSupply.
- Impact: A user with authorization for a claim can mint any quantity up to the remaining supply, exceeding the intended per-claim or per-user allocation.

## Global Merkle root can be overwritten by later art
- Location: src/PhiFactory.sol : _initializePhiArt / merkleClaim
- Mechanism: credMerkleRoot[credChainId][credId] is shared by all art for a cred, and _initializePhiArt overwrites it on every art creation. merkleClaim for older art reads the latest global root, not the root that existed when that art was created.
- Impact: Creating later art for the same cred can invalidate previous claim proofs or replace the eligibility set for earlier Merkle-gated art.

## Updating art settings can reopen ended mint windows
- Location: src/PhiFactory.sol : updateArtSettings
- Mechanism: updateArtSettings rejects endTime_ < block.timestamp for every update, even when the artist only wants to change URI, royalties, or soulBounded after the mint ended. Since claim only reverts when block.timestamp > art.endTime, setting endTime_ to the current block reopens claims for that block.
- Impact: A malicious user can backrun an artist’s post-mint settings update and mint after the intended claim period has ended.

## Artists can mutate critical NFT terms after mint
- Location: src/PhiFactory.sol : updateArtSettings
- Mechanism: The artist can later change URI, receiver, maxSupply, mintFee, startTime, endTime, soulBounded, and royalties without holder consent or meaningful bounds.
- Impact: Existing holders can be rugged by changed metadata, newly soulbound transfer restrictions, altered supply windows, or unexpectedly high royalty settings.

## Historical zero-balance holders can DoS curator reward distribution
- Location: src/Cred.sol : _updateCuratorShareBalance / _getCuratorData; src/reward/CuratorRewardsDistributor.sol : distribute
- Mechanism: When a holder sells to zero, shareBalance[credId].set(holder, 0) leaves the holder key in the EnumerableMap. getCuratorAddresses iterates all historical keys, and distribute depends on that full enumeration.
- Impact: An attacker can churn many addresses through buy/sell cycles to permanently bloat the map, causing curator reward distribution to run out of gas and locking rewards for that cred.

## Public share-index helpers let anyone corrupt holder state
- Location: src/Cred.sol : _addCredIdPerAddress / _removeCredIdPerAddress
- Mechanism: Both bookkeeping helpers are public and accept an arbitrary sender_ address. They mutate _credIdsPerAddress and index mappings without checking authorization or synchronizing with shareBalance.
- Impact: An attacker can corrupt a victim’s position index, causing future full sells or position enumeration to revert or return incorrect data.

## buyShareCredFor can grief-lock a victim’s position
- Location: src/Cred.sol : buyShareCredFor / _handleTrade
- Mechanism: Anyone can buy shares for any curator_, and the buy branch sets lastTradeTimestamp[credId][curator_] = block.timestamp for the entire position.
- Impact: An attacker can repeatedly buy a minimal amount for a victim to reset the victim’s lock timer and prevent them from selling during price moves.

## Buy refund reentrancy bypasses the share lock
- Location: src/Cred.sol : _handleTrade
- Mechanism: The buy path credits shares and increases supply, then refunds excess ETH before setting lastTradeTimestamp. A contract buyer can overpay, receive the refund callback, and reenter sellShareCred or distribute-related flows while the new shares are credited but the lock timestamp is still stale.
- Impact: The 10-minute SHARE_LOCK_PERIOD can be bypassed, enabling same-transaction buy/distribute/sell strategies that the lock is intended to prevent.

## Cred creation does not bind the creator to the signed payload
- Location: src/Cred.sol : createCred
- Mechanism: The signed payload covers sender, bonding curve, URL, type, verification type, and Merkle root, but creator_ is supplied separately and is not checked against the signed data or msg.sender.
- Impact: A valid creation authorization can be used to create a cred with an unauthorized creator/royalty recipient, redirecting future creator fees.

