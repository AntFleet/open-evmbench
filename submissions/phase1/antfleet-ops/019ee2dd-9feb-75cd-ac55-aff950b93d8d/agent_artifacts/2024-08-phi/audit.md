# Audit: 2024-08-phi

 ## Signed art-creation payload does not cover `CreateConfig` and is replayable
- Location: `PhiFactory.sol` : `createArt` (`_validateArtCreationSignature`, `_createERC1155Data`, `createERC1155Internal`)
- Mechanism: `_validateArtCreationSignature` only verifies the signature over `(expiresIn, uri, credData)`. The `CreateConfig` argument supplied by the caller—`artist`, `receiver`, `maxSupply`, `mintFee`, `startTime`, `endTime`, and `soulBounded`—is never authenticated. In addition, `signedData_` contains no nonce, salt, or chain id, so the same signature can be reused indefinitely until expiry.
- Impact: Anyone holding a valid creation signature can mint unlimited art instances for a cred and choose arbitrary economics/permissions, e.g. set themselves as `artist`/`receiver` to collect mint fees and royalties, hijack `onlyArtCreator` privileges, or shadow legitimate art for a cred.

## Share-lock period can be bypassed via reentrancy on buy
- Location: `Cred.sol` : `_handleTrade` (called by `buyShareCred`, `buyShareCredFor`)
- Mechanism: In the buy branch, `_updateCuratorShareBalance` and `cred.currentSupply` are updated, then excess ETH is refunded to `_msgSender()` (and protocol/creator fees are transferred) before `lastTradeTimestamp[credId_][curator_]` is written. A buyer contract that overpays therefore receives a refund before the timestamp is set and can reenter `sellShareCred`; the sell-side lock check still sees the old timestamp (or `0`), so it passes.
- Impact: Curators can buy and immediately sell shares in the same transaction, completely circumventing the intended `SHARE_LOCK_PERIOD`.

## Curator bookkeeping helpers are externally callable
- Location: `Cred.sol` : `_addCredIdPerAddress` and `_removeCredIdPerAddress`
- Mechanism: Both functions are declared `public` instead of `internal`, so any account can directly mutate `_credIdsPerAddress`, `_credIdExistsPerAddress`, and `_credIdsPerAddressArrLength`. `_updateCuratorShareBalance` assumes these mappings stay consistent with `shareBalance`.
- Impact: An attacker can corrupt a curator’s position list, add fake cred entries, remove legitimate entries, and cause subsequent sell-all transactions to revert because `_removeCredIdPerAddress` is invoked on an already-empty array.

## Protocol fee has no upper bound
- Location: `Cred.sol` : `setProtocolFeePercent`; `BondingCurve.sol` : `_getProtocolFee`
- Mechanism: `setProtocolFeePercent` accepts any `uint256` with no cap. `BondingCurve._getProtocolFee` computes `price * protocolFeePercent / RATIO_BASE`. If `protocolFeePercent` is set above `RATIO_BASE`, the sell path in `_handleTrade` computes `price - protocolFee - creatorFee`, which underflows and reverts.
- Impact: A compromised or malicious owner can set a fee above 100%, freezing all sell activity and forcing buyers to pay more than the share price in fees.

## Signed cred-creation payload is replayable
- Location: `Cred.sol` : `createCred`
- Mechanism: `createCred` checks that the `sender` field in `signedData_` matches `msg.sender`, but the signed payload has no nonce, salt, chain id, or cred-id binding and is not invalidated after use. The same valid signature can therefore be replayed repeatedly by the same sender until `expiresIn`.
- Impact: A single signed authorization can create any number of duplicate creds, inflating the registry, and the unsigned `buyShareRoyalty_`/`sellShareRoyalty_` can be changed on each replay.

## `handleRewardsAndGetValueSent` lacks caller restriction
- Location: `PhiRewards.sol` : `handleRewardsAndGetValueSent`
- Mechanism: The function is `external payable` but has no `onlyFactory`/`onlyNFT` access control. It performs the full reward split—crediting artist/referral/verifier balances and, when `chainSync_` is true, depositing curator rewards into `CuratorRewardsDistributor`—and only requires `msg.value == computeMintReward(...)`.
- Impact: Anyone can call it with arbitrary `artId_`, `credId_`, and `addressesData_` to attribute rewards and inflate `CuratorRewardsDistributor` balances without a corresponding NFT mint, breaking the accounting link between mints and rewards.
