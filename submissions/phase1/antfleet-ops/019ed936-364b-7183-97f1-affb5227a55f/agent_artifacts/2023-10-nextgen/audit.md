# Audit: 2023-10-nextgen

## Consensus findings

## ERC721 receiver reentrancy in `mint` bypasses per-mint accounting and rate limits
*(consensus)*
- Location: `MinterContract.sol` : `mint` (the mint `for` loop and the trailing `salesOption == 3` block); `NextGenCore.sol` : `mint`, `_mintProcessing` → `_safeMint`
- Mechanism: Tokens are minted via `gencore.mint(...)`, which calls `_safeMint(_mintTo, ...)` and invokes the recipient's `onERC721Received` callback **before** `mint` updates its accounting. The per-wallet counters `tokensMintedAllowlistAddress` / `tokensMintedPerAddress`, and (for drip sales) `lastMintDate[col]` and `collectionTotalAmount[col]`, are all written only after the loop completes. A malicious `_mintTo` contract re-enters `mint` from `onERC721Received` while these values are still stale: the per-wallet limit check still passes, and for `salesOption == 3` the `tDiff >= 1` check against the un-advanced `lastMintDate[col]` still passes, allowing recursive minting.
- Impact: A contract wallet can mint more than its allowlist or public-sale per-wallet maximum in a single transaction, and can fully defeat the `salesOption == 3` "1 mint per time-period" anti-whale limit (minting the entire remaining supply in one tx, paying the escalating `getPrice` but ignoring the rate limit). The same stale accounting applies to a delegator's allowance on delegated allowlist mints, and leaves `collectionTotalAmount` updated out of order with the mints.

## Synchronous NXT randomizer enables trait grinding / free rerolls
*(consensus)*
- Location: `RandomizerNXT.sol` : `calculateTokenHash`; `NextGenCore.sol` : `_mintProcessing`; `XRandoms.sol` : `randomNumber` / `randomWord`
- Mechanism: `_mintProcessing` calls the randomizer and stores the token hash **before** `_safeMint` invokes the recipient callback. With `NextGenRandomizerNXT`, `calculateTokenHash` derives the hash synchronously from `block.prevrandao`, `blockhash(block.number-1)`, `block.timestamp` and `_mintIndex` — all known to the caller within the same transaction. A wrapper contract (or the receiving contract in its `onERC721Received` hook) can read `tokenToHash` / `retrieveTokenHash(_mintIndex)`, compute the resulting generative-art traits, and revert on an undesirable outcome at gas-only cost.
- Impact: Token rarity is predictable and grindable; an attacker can selectively keep rare mints and discard undesirable ones, breaking randomness fairness for any collection using the NXT randomizer. (Affects only the NXT randomizer path, not the VRF/arrng paths.)

## NFT transfer failure at settlement permanently locks auction funds
*(consensus)*
- Location: `AuctionDemo.sol` : `claimAuction(uint256)`; `MinterContract.sol` : `mintAndAuction(...)`
- Mechanism: The auctioned NFT is held by the `mintAndAuction` recipient (`ownerOfToken = IERC721(gencore).ownerOf(_tokenId)`), not by the auction contract. `claimAuction` performs `safeTransferFrom(ownerOfToken, highestBidder, _tokenid)` and only then refunds the losing bidders in the same call. `participateToAuction` never requires bidders to be able to receive ERC721s. If the recipient never approved the auction contract, transferred/sold the token, or the highest bidder is a contract that rejects `onERC721Received`, the `safeTransferFrom` reverts — reverting the entire `claimAuction`. After `block.timestamp > auctionEndTime`, `cancelBid` / `cancelAllBids` also revert ("Auction ended").
- Impact: All non-cancelled bids plus the winner's funds become permanently locked in the auction contract, with no admin rescue/withdraw path. Reachable both by a malicious highest bidder (a contract that leaves an un-receivable bid active until close) and by simple operational error (missing approval or a sold/transferred token).

---

## Additional findings (single-reviewer)

## Same-timestamp double-withdrawal / reentrancy in `claimAuction`
*(Reviewer A only)*
- Location: `AuctionDemo.sol` : `claimAuction(uint256)`, plus `cancelBid` / `cancelAllBids`
- Mechanism: `claimAuction` requires `block.timestamp >= getAuctionEndTime` while `cancelBid` / `cancelAllBids` require `block.timestamp <= getAuctionEndTime`, so all are callable in the boundary block where `timestamp == auctionEndTime`. `claimAuction` refunds every bidder (`payable(...).call{value: bid}`) but **never sets `auctionInfoData[_tokenid][i].status = false`**. Its only re-entry guard, `auctionClaim[_tokenid]`, is not checked by `cancelBid` / `cancelAllBids`, and there is no `nonReentrant` modifier or CEI ordering on the refund loop. A bidder already refunded inside `claimAuction` still has `status == true` and can call `cancelBid(_tokenid, index)` (in the same block, or by re-entering during the refund `.call`) to be paid a second time.
- Impact: At the auction-end boundary block, any losing bidder (or the winner, who also keeps lower bids in the array) can withdraw their escrowed bid twice, draining ETH owed to other bidders / the owner's proceeds. A searcher/miner can order `claimAuction` then `cancelBid` in the same block, or a malicious bidder contract can re-enter `cancelBid` from its refund `receive()`.

## Function-admin permissions scoped by selector only → cross-contract privilege escalation
*(Reviewer A only)*
- Location: `NextGenAdmins.sol` : `registerFunctionAdmin` / `retrieveFunctionAdmin`, consumed by every `FunctionAdminRequired(this.X.selector)` modifier
- Mechanism: Function-admin rights are stored as `functionAdmin[address][bytes4 selector]`, keyed only by the 4-byte selector with no contract-address component. Distinct contracts expose functions with identical signatures and therefore identical selectors — e.g. `updateAdminContract(address)`, `updateCoreContract(address)`, and `emergencyWithdraw()` exist in `MinterContract`, `NextGenCore`, `RandomizerVRF`, and `RandomizerRNG`. Granting function-admin for a selector on one contract silently authorizes it on every contract sharing that selector.
- Impact: An admin intending to grant narrow rights on a single contract unknowingly grants the same rights everywhere the selector collides — e.g. swapping the core/admin contract pointer or triggering `emergencyWithdraw` across multiple contracts — a privilege-scoping/escalation flaw in the access-control layer the whole system depends on.

## `emergencyWithdraw` lets any function admin seize all minting proceeds
*(Reviewer A only)*
- Location: `MinterContract.sol` : `emergencyWithdraw()`
- Mechanism: `emergencyWithdraw` is gated only by `FunctionAdminRequired` (any global or function admin, not just the owner) and sends `address(this).balance` to `adminsContract.owner()`. The minter's balance is the sum of all per-collection `collectionTotalAmount[...]` escrowed for `payArtist` splits, but the withdrawal never touches `collectionTotalAmount`, bypassing the artist/team split logic entirely.
- Impact: A single function admin can drain 100% of accumulated mint revenue — including the portion owed to artists with an accepted royalty split — to the admin-contract owner, without artist consent. Combined with the selector-scoped grant flaw above, the set of addresses able to do this is broader than intended.

## Expired delegations remain fully usable
*(Reviewer B only)*
- Location: `NFTdelegation.sol` : `retrieveGlobalStatusOfDelegation`, `registerDelegationAddressUsingSubDelegation`, `revokeDelegationAddressUsingSubdelegation`; `MinterContract.sol` : `mint`, `burnOrSwapExternalToMint`
- Mechanism: Delegation records store `expiryDate`, `allTokens`, and token ids, but the authorization paths used by the minter only check whether a delegation hash array has any entry. Expiration and token scope are ignored, and subdelegation checks consult historical delegator arrays rather than active, unexpired records.
- Impact: A previously delegated hot wallet or subdelegate keeps privileges after expiry unless explicitly revoked. With a valid allowlist proof it can mint against the delegator's allowance to an arbitrary `_mintTo`; for external burn/swap flows it can consume an owner's approved NFT after the delegation has expired.

## Cancelled-bid spam can make auction settlement uncallable (gas DoS)
*(Reviewer B only)*
- Location: `AuctionDemo.sol` : `participateToAuction`, `cancelBid`, `cancelAllBids`, `claimAuction`, `returnHighestBid`, `returnHighestBidder`
- Mechanism: Every bid is permanently appended to `auctionInfoData`, while cancellation only flips `status` to `false`. `claimAuction`, `returnHighestBid`, and `returnHighestBidder` iterate over the entire historical array, including inactive (cancelled) bids.
- Impact: An attacker can submit many increasing bids, cancel them before the auction ends to recover the ETH, and leave a large inactive bid history. Settlement iteration can then exceed the block gas limit, permanently locking the NFT and all active auction funds.

## `collectionCirculationSupply` incremented before the supply-cap guard (low severity)
*(Reviewer A only)*
- Location: `NextGenCore.sol` : `mint`, `airDropTokens`
- Mechanism: Both functions increment `collectionCirculationSupply` before the `if (totalSupply >= circulationSupply)` guard. When invoked exactly at the cap, the counter is bumped without a corresponding mint, drifting `viewCirSupply` from the true minted count. Normal flow pre-checks supply in the minter, so it isn't reached in practice, but the core function is not self-consistent if called directly at the boundary.
- Impact: Supply accounting can drift from the actual minted count at the cap boundary; no direct fund loss, but a correctness/invariant defect in core minting.

## `updateUseCaseCounter()` has no access control (low severity)
*(Reviewer A only)*
- Location: `DelegationManagementContract.sol` : `updateUseCaseCounter()`
- Mechanism: The function has no access-control modifier, so anyone can call it to monotonically inflate `useCaseCounter`.
- Impact: An attacker can arbitrarily widen the range of acceptable `_useCase` values. Impact is limited (no fund loss), but it is an unrestricted state mutation.

---

*Note (Reviewer A, not classified as exploitable):* In `AuctionDemo.returnHighestBidder`, the running `highBid` is never updated inside the loop. Reviewer A assessed this as masked by the strictly-increasing-bid invariant enforced in `participateToAuction`, so it is not currently exploitable; recorded here for completeness rather than as an active finding.

