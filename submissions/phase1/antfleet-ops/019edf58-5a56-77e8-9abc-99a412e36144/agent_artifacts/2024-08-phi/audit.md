# Audit: 2024-08-phi

# Security Audit Report

## Missing Mint Replay Protection
- Location: `PhiFactory.sol` : `_validateAndUpdateClaimState`
- Mechanism: The function sets `artMinted[artId_][minter_] = true` and `credMinted[art.credChainId][art.credId][minter_] = true` but never checks whether either flag is already set before proceeding. There is no `require(!artMinted[...])` guard. Both the signature-claim path and the merkle-claim path call this function once per claim, but nothing prevents the same minter from calling `claim`/`signatureClaim`/`merkleClaim` repeatedly with the same valid signature or merkle proof. The signature in `signatureClaim` contains no nonce, and the merkle proof is static, so both are infinitely replayable.
- Impact: Any authorized minter can mint the same art token an unlimited number of times (up to `maxSupply`), monopolizing the entire supply of any art. This defeats the intended one-claim-per-user model and allows a single attacker to claim all tokens of any art, denying access to other legitimate users.

## Unsigned CreateConfig Allows Art Hijacking
- Location: `PhiFactory.sol` : `createArt`
- Mechanism: `createArt` validates the signature over `signedData_` which is decoded as `(uint256 expiresIn, string uri, bytes credData)`. The `CreateConfig memory createConfig_` — containing `artist`, `receiver`, `maxSupply`, `mintFee`, `startTime`, `endTime`, `soulBounded` — is passed as a separate unsigned parameter. The phi signer's signature does not cover any of these critical fields. An attacker who obtains a valid `(signedData_, signature_)` pair (e.g. from a backend API) can submit it with a malicious `createConfig_` that sets themselves as the `artist` and `receiver`.
- Impact: An attacker can create art contracts with arbitrary configuration: redirect mint-fee revenue to their own `receiver` address, set themselves as `artist` (gaining royalty-update privileges via `onlyArtCreator`), set unlimited `maxSupply`, or set abusive `mintFee` values. The cred association is authenticated, but all economic parameters of the art are attacker-controlled.

## Excess ETH Permanently Lost in PhiFactory
- Location: `PhiFactory.sol` : `claim` / `batchClaim` / `createArt`
- Mechanism: `claim` receives `msg.value` but only forwards `getArtMintFee(artId, quantity)` to `this.merkleClaim`/`this.signatureClaim`. Any excess `msg.value - mintFee` is never refunded to the caller and remains stuck in the factory contract. In `batchClaim`, each `this.claim{value: ethValue_[i]}` call has the same problem: if `ethValue_[i]` exceeds the actual mint fee, the difference is trapped. Similarly, `createArt` forwards all `msg.value` to the cloned NFT contract, which refunds the excess to `_msgSender()` (the factory), not to the original user. The trapped ETH is only recoverable by the owner via `withdraw()`.
- Impact: Users who overpay (intentionally or due to fee changes between transaction submission and execution) permanently lose the excess ETH. In `batchClaim`, users must pre-compute exact fees for every item; any miscalculation results in lost funds.

## Public State-Corrupting Index Functions
- Location: `Cred.sol` : `_addCredIdPerAddress` / `_removeCredIdPerAddress`
- Mechanism: These functions are declared `public` despite being internal helpers that modify the `_credIdsPerAddress`, `_credIdsPerAddressCredIdIndex`, and `_credIdsPerAddressArrLength` storage mappings. There is no access control. Any external caller can invoke `_addCredIdPerAddress(credId, victim)` to inject arbitrary cred IDs into a victim's position list, or `_removeCredIdPerAddress` to remove entries, desynchronizing the per-address cred-ID index from the actual `shareBalance` EnumerableMap.
- Impact: An attacker can corrupt the position-tracking data structures for any address, causing `getPositionsForCurator` to return incorrect data (phantom positions or missing positions). This breaks off-chain integrations that rely on position queries and can cause downstream accounting errors in any system that reads curator positions.

## Out-of-Bounds Array Write in getPositionsForCurator
- Location: `Cred.sol` : `getPositionsForCurator`
- Mechanism: The result arrays are allocated with size `stopIndex - start_`, but the write loop uses the absolute loop index `i` (starting at `start_`) instead of the relative index `index` to write into them: `credIds[i] = credId; amounts[i] = amount;`. When `start_ > 0`, the first write targets `credIds[start_]` which is beyond the array bounds (valid indices are `0` to `stopIndex - start_ - 1`), causing an out-of-bounds array access that reverts in Solidity 0.8.x.
- Impact: The `getPositionsForCurator` view function is completely non-functional for any query with `start_ > 0`, making pagination impossible. Any caller attempting to paginate curator positions will have their call revert.

## No Upper Bound on Protocol Fee Percent
- Location: `Cred.sol` : `setProtocolFeePercent`
- Mechanism: `setProtocolFeePercent` sets `protocolFeePercent` without any maximum check (unlike `PhiFactory.setProtocolFee` which caps at 10_000). The protocol fee is computed as `price * protocolFeePercent / 10_000` in the bonding curve. Combined with creator royalties (up to 5000 bps via `MAX_ROYALTY_RANGE`), if `protocolFeePercent + sellShareRoyalty > 10_000`, the sell payout calculation `price - protocolFee - creatorFee` underflows and reverts.
- Impact: If the owner sets `protocolFeePercent` above 5000 for a cred with 5000 bps sell royalty (or above 10000 generally), all sells for that cred become impossible, permanently locking shareholders' funds. Even moderate misconfiguration can render selling impossible.
