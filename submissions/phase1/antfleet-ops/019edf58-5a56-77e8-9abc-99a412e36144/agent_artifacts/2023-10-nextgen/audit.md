# Audit: 2023-10-nextgen

## Auction proceeds routed to contract owner instead of NFT owner
- Location: `AuctionDemo.sol` : `claimAuction`
- Mechanism: The highest bid is sent via `payable(owner()).call{value: highestBid}("")` where `owner()` is the Ownable owner of the `auctionDemo` contract (the deployer), not the owner of the auctioned NFT (the artist/recipient from `mintAndAuction`). The token owner receives nothing while the contract deployer receives all auction proceeds.
- Impact: An attacker who deploys the auction contract (or the fixed deployer) receives all auction revenue that should go to the NFT owner/artist. Every auction settlement misappropriates the winning bid.

## Failed ETH transfers in claimAuction silently succeed (permanent fund loss)
- Location: `AuctionDemo.sol` : `claimAuction`
- Mechanism: Both the owner payment and loser refunds use `(bool success, ) = payable(...).call{value: ...}("")` but the return value `success` is only emitted in an event—never required. If any `.call` fails, the function continues, sets `auctionClaim[_tokenid] = true`, and the ETH is permanently stuck in the contract with no retry path.
- Impact: Any losing bidder whose receive logic reverts (e.g. a contract wallet that rejects ETH) permanently loses their bid funds. The owner can also lose the winning bid if their address rejects the transfer.

## NFT transfer in claimAuction will always revert (no approval mechanism)
- Location: `AuctionDemo.sol` : `claimAuction`
- Mechanism: `IERC721(gencore).safeTransferFrom(ownerOfToken, highestBidder, _tokenid)` is called by the `auctionDemo` contract. The auction contract is neither the token owner nor an approved operator, and there is no code path that calls `setApprovalForAll` or `approve` on the gencore contract for the auction contract. The `safeTransferFrom` will revert with "caller is not token owner or approved."
- Impact: Auctions can never be settled—the winner can never receive the NFT and the entire auction flow is broken.

## Expired delegations still accepted as valid
- Location: `MinterContract.sol` : `mint`, `burnOrSwapExternalToMint` (via `DelegationManagementContract.retrieveGlobalStatusOfDelegation`)
- Mechanism: `retrieveGlobalStatusOfDelegation` returns `globalDelegationHashes[hash].length > 0`—it only checks that a delegation entry exists, never comparing `expiryDate` against `block.timestamp`. The minter uses this function to authorize delegated minting, so a delegation that has past its expiry date is still treated as active.
- Impact: A delegated hot-wallet can mint on behalf of a delegator's allowlist allocation indefinitely after the delegation expiry, consuming the delegator's mint allowance without consent.

## `payArtist` team payment addresses and percentages are admin-controlled at call time
- Location: `MinterContract.sol` : `payArtist`
- Mechanism: `_team1`, `_team2`, `_teamperc1`, `_teamperc2` are function parameters passed at call time by any `FunctionAdmin`. The only constraint is that the percentages sum to 100 with the artist split. A function admin can specify arbitrary addresses for the team cut, redirecting up to `100 - artistPercentage`% of all collected mint revenue to addresses they control.
- Impact: A compromised or malicious function admin can steal the team portion (and, if the artist percentage was set low, the majority) of all primary sale revenue for any collection.

## `updateUseCaseCounter` has no access control
- Location: `NFTdelegation.sol` : `updateUseCaseCounter`
- Mechanism: `updateUseCaseCounter()` is a public function with no modifier or `msg.sender` check. Anyone can call it to increment `useCaseCounter`, which gates the maximum allowed use-case ID in `registerDelegationAddress` (`require(_useCase <= useCaseCounter)`).
- Impact: Any caller can inflate the use-case counter, allowing registration of arbitrary new use-case IDs. While not directly destructive, it bypasses the intended governance gate for introducing new delegation use cases.

## Predictable on-chain randomness in RandomizerNXT
- Location: `RandomizerNXT.sol` : `calculateTokenHash` (and `XRandoms.sol` : `randomNumber`/`randomWord`)
- Mechanism: The token hash is derived from `keccak256(abi.encodePacked(_mintIndex, blockhash(block.number - 1), randoms.randomNumber(), randoms.randomWord()))`. The `XRandoms` contract computes its values from `block.prevrandao`, `blockhash(block.number - 1)`, and `block.timestamp`—all of which are observable/manipulable by a validator in the same block.
- Impact: A validator or sophisticated attacker can predict or influence the generated hash, allowing them to pre-determine the token's generative art output and selectively mint desirable tokens.
