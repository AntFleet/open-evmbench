# Audit: 2024-08-phi

## Public Share-Index Helpers Let Anyone Corrupt Holder State
- Location: `src/Cred.sol` : `_addCredIdPerAddress`, `_removeCredIdPerAddress`
- Mechanism: Both functions are `public` bookkeeping helpers but have no access control and do not verify that `msg.sender` owns or is authorized to mutate `sender_`’s position index. An attacker can remove another holder’s `credId` from `_credIdsPerAddress` or insert bogus/duplicate entries without changing the actual `shareBalance`.
- Impact: An attacker can corrupt another user’s position index and make future full sells revert in `_updateCuratorShareBalance` when it tries to remove the position again. This can grief holders by blocking full liquidation and corrupting position enumeration.

## Individual Buys Can Reenter Before The Share Lock Is Set
- Location: `src/Cred.sol` : `_handleTrade`
- Mechanism: In the buy path, the contract updates balances and supply, then refunds excess ETH to `_msgSender()`, and only after that sets `lastTradeTimestamp[credId_][curator_]`. A malicious buyer can deliberately overpay, receive the refund in a fallback, and reenter `sellShareCred` while the newly bought shares are already credited but the lock timestamp is still old.
- Impact: The 10-minute `SHARE_LOCK_PERIOD` can be bypassed for individual buys, allowing same-transaction buy-and-sell cycles that the lock is intended to prevent.

## Zero-Balance Holders Are Never Removed From The EnumerableMap
- Location: `src/Cred.sol` : `_updateCuratorShareBalance`; `src/reward/CuratorRewardsDistributor.sol` : `distribute`
- Mechanism: When a holder sells all shares, `shareBalance[credId_].set(sender_, 0)` is used instead of removing the key from the `EnumerableMap`. `getCuratorAddresses` must still iterate over every historical holder and filter zero balances. `CuratorRewardsDistributor.distribute` depends on this enumeration.
- Impact: An attacker can churn many addresses through buy/sell cycles to permanently bloat the holder map. Reward distribution and curator address reads can become too expensive or revert out-of-gas, locking curator rewards for that cred.

## Cred Creation Signatures Do Not Bind Creator Or Royalties
- Location: `src/Cred.sol` : `createCred`
- Mechanism: The signed payload only covers `expiresIn`, `sender`, bonding curve, URL, cred type, verification type, and merkle root. The externally supplied `creator_`, `buyShareRoyalty_`, and `sellShareRoyalty_` are not signed. Any caller with a valid signer authorization for the decoded `sender` can choose arbitrary creator and royalty values up to the contract maximum.
- Impact: Authorized creation signatures can be abused to create creds with unauthorized attribution and fee settings, allowing spoofed creator identity and unexpected royalty extraction from future traders.

## Cred Signatures Are Replayable Until Expiry
- Location: `src/Cred.sol` : `createCred`, `updateCred`
- Mechanism: The contract verifies the signer and expiry but does not consume a nonce, mark a digest as used, or otherwise bind a signature to a single action. The unused decoded integer is not checked or stored.
- Impact: A valid `createCred` signature can be replayed repeatedly until expiry to create multiple creds from the same authorization. A valid `updateCred` authorization can also be reused by the creator, including with different unsigned royalty parameters.

## Art Creation Signatures Do Not Bind Economic Or Control Parameters
- Location: `src/PhiFactory.sol` : `createArt`, `_createERC1155Data`
- Mechanism: `_validateArtCreationSignature` verifies only `signedData_`, which decodes to `(expiresIn, uri, credData)`. The `CreateConfig` fields are not signed: `artist`, `receiver`, `maxSupply`, `mintFee`, `startTime`, `endTime`, and `soulBounded` are all caller-controlled.
- Impact: Anyone with a valid art creation signature can create an art with themselves as artist/receiver, arbitrary mint economics, arbitrary supply, and arbitrary transferability settings. This gives the attacker control over art settings and reward receiver selection that the signer did not authorize.

## Art Creation Signatures Are Front-Runnable And Replayable
- Location: `src/PhiFactory.sol` : `createArt`
- Mechanism: The art creation signature does not bind `msg.sender`, the factory address, the chain ID, or a consumed nonce/art ID. Since `artIdCounter` is assigned on-chain and no digest is marked used, the same signed payload can be submitted by anyone and reused until expiry.
- Impact: An attacker who sees or obtains a valid creation payload can front-run the intended creator or replay it to create multiple art IDs for the same signed authorization.

## Claim State Does Not Enforce One Claim Per Minter
- Location: `src/PhiFactory.sol` : `_validateAndUpdateClaimState`
- Mechanism: The function sets `artMinted[artId_][minter_] = true` and `credMinted[...] = true`, but never checks whether either value was already true. The declared `AddressAlreadyMinted` error is unused.
- Impact: The same eligible minter can claim the same art repeatedly until `maxSupply` is exhausted, draining mint supply and repeatedly triggering reward accounting.

## Claim Quantity Is Not Authorized
- Location: `src/PhiFactory.sol` : `signatureClaim`, `merkleClaim`
- Mechanism: For signature claims, the signed `encodeData_` excludes `mintArgs_.quantity`; for merkle claims, the verified leaf is based on `minter_` and `leafPart_`, not quantity. The contract only checks that the requested quantity is nonzero and does not exceed remaining supply.
- Impact: A user with a valid claim authorization for one mint can request any quantity up to the remaining `maxSupply`, minting more NFTs and causing more rewards to be paid than intended.

## Signature Claims Are Cross-Chain Replayable
- Location: `src/PhiFactory.sol` : `signatureClaim`
- Mechanism: `signatureClaim` decodes a chain ID from `encodeData_` but discards it and never checks it equals `block.chainid`. The recovered signature is therefore valid for whatever chain ID was included in the signed bytes.
- Impact: If the same signer and compatible art IDs exist on another chain, a claim signature issued for one chain can be replayed directly against another chain’s factory.

## Factory Claim Wrapper Can Spend The Factory’s Existing ETH
- Location: `src/PhiFactory.sol` : `claim`
- Mechanism: `claim` computes `mintFee` and calls `this.merkleClaim{value: mintFee}` or `this.signatureClaim{value: mintFee}` without checking that the caller supplied at least `mintFee`. If the factory already holds ETH, the self-call pays the missing amount from the factory balance.
- Impact: Any ETH accidentally or intentionally left in `PhiFactory` can be drained to subsidize attacker claims. The attacker can mint without paying the full fee and route any available referral/reward portions according to the claim path.

## Merkle Roots Are Global Per Cred And Can Be Overwritten By Later Art
- Location: `src/PhiFactory.sol` : `_initializePhiArt`, `merkleClaim`
- Mechanism: `credMerkleRoot[credChainId][credId]` is shared across all art for the same cred. Every art creation overwrites this global root, while `merkleClaim` for any merkle art reads the current global root instead of an art-specific root.
- Impact: Creating a later art for the same cred can invalidate or replace the eligibility set for earlier merkle-gated art. This can deny legitimate users’ claims or make claims validate against a different root than the one intended when the art was created.

