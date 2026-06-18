# Audit: 2024-08-phi

## 1. Unprotected `_addCredIdPerAddress` and `_removeCredIdPerAddress` allow arbitrary manipulation of curator tracking data

- **Location**: `src/Cred.sol` : `_addCredIdPerAddress`, `_removeCredIdPerAddress`
- **Mechanism**: These functions are declared `public` (instead of `internal`) and do not verify that `msg.sender` is authorized to modify the `sender_` address’s data. An attacker can call them directly to add or remove any `credId` for any curator, corrupting the `_credIdsPerAddress` array, the `_credIdExistsPerAddress` flag, and the index mapping. The `_addCredIdPerAddress` function does not set the existence flag, while `_removeCredIdPerAddress` does not clear it, leading to inconsistent state.
- **Impact**: An attacker can corrupt the data used by `getPositionsForCurator`, causing incorrect or missing position information for any curator. The attacker can also cause the array length and index to desync, leading to out‑of‑bounds reverts or permanent DoS of the curator position tracking system.

## 2. Reentrancy allows bypass of the 10‑minute lock period between buy and sell

- **Location**: `src/Cred.sol` : `_handleTrade` (buy branch)
- **Mechanism**: The `_handleTrade` function lacks a reentrancy guard. When buying, it sends excess ETH to the caller (`_msgSender().safeTransferETH(excessPayment)`) **before** updating `lastTradeTimestamp`. An attacker can re‑enter from their fallback function during this transfer and call `sellShareCred`, which checks `lastTradeTimestamp` (still at the old value, possibly zero) and succeeds immediately, bypassing the `SHARE_LOCK_PERIOD` of 10 minutes.
- **Impact**: The lock period intended to prevent rapid round‑tripping of shares is completely circumvented. An attacker can buy and sell in the same transaction, enabling market manipulation and potentially extracting value from the bonding curve.

## 3. Signature replay in `createCred` and `updateCred` allows multiple creations/updates with the same authorization

- **Location**: `src/Cred.sol` : `createCred`, `updateCred`
- **Mechanism**: The signatures used to authorize credential creation and updates contain only an expiration timestamp and the sender’s address, but no nonce or unique identifier. The same valid signature can be replayed by the designated sender (or anyone who obtains it) as long as the timestamp has not expired. The `createCred` function does not check whether the cred already exists, so each call creates a new cred with a new `credId`.
- **Impact**: An attacker can spam the protocol with many identical credentials, exhausting storage and front‑end resources. For `updateCred`, repeated updates can overwrite the same cred’s metadata, causing confusion but limited direct financial harm.

## 4. Signature replay in `createArt` allows unlimited art creation with the same authorization

- **Location**: `src/PhiFactory.sol` : `createArt`
- **Mechanism**: The signature checked in `_validateArtCreationSignature` includes only `expiresIn_`, `uri_`, and `credData`. There is no nonce or chain‑specific identifier. The same signature can be used repeatedly to call `createArt`, each time incrementing `artIdCounter` and deploying a new art contract linked to the same credential.
- **Impact**: An attacker can create an arbitrary number of art contracts tied to the same credential, flooding the factory with useless clones and exhausting the art ID namespace.

## 5. DoS in `CuratorRewardsDistributor.distribute` due to unbounded curator list

- **Location**: `src/reward/CuratorRewardsDistributor.sol` : `distribute`
- **Mechanism**: The function calls `credContract.getCuratorAddresses(credId, 0, 0)` to retrieve *all* curators without pagination, then iterates over the entire list to compute and distribute rewards. If a credential has a large number of curators, the transaction gas cost will exceed the block gas limit, making the function uncallable.
- **Impact**: All rewards accumulated for that credential become permanently locked; no one can trigger the distribution, and the ETH remains stuck in the contract.

## 6. Stale `protocolFeeDestination` in `PhiNFT1155` after factory updates

- **Location**: `src/art/PhiNFT1155.sol` : `initialize` → `createArtFromFactory`
- **Mechanism**: During NFT contract initialization, `protocolFeeDestination` is set to the factory’s current `protocolFeeDestination`. If the factory owner later changes the destination via `setProtocolFeeDestination`, the NFT contract retains the old address. The `createArtFromFactory` function sends the art creation fee to this stored address, not the factory’s updated one.
- **Impact**: Art creation fees will be sent to an outdated address, potentially causing loss of funds if the old destination is no longer controlled or intended to receive fees.
