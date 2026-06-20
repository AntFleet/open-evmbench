# Audit: 2023-10-nextgen

I found these genuine vulnerabilities. The source tree appears duplicated under `hardhat/smart-contracts` and `smart-contracts`; locations below use `smart-contracts`, with the same issues applying to the duplicate files.

## Safe-mint reentrancy bypasses mint limits
- Location: `smart-contracts/MinterContract.sol` : `mint`; `smart-contracts/NextGenCore.sol` : `mint` / `_mintProcessing`
- Mechanism: `NextGenMinterContract.mint` calls `gencore.mint`, which calls `_safeMint` before `NextGenCore.mint` increments `tokensMintedAllowlistAddress` / `tokensMintedPerAddress`, and before the minter updates `lastMintDate` for sales option 3. A malicious contract used as `_mintTo` receives `onERC721Received` during `_safeMint` and can reenter `NextGenMinterContract.mint` while the per-address mint counters and period gate still reflect the pre-mint state.
- Impact: An attacker can mint more than their allowlist/public-sale allowance and can bypass the intended one-mint-per-period restriction for sales option 3, acquiring more scarce tokens than allowed.

## NXT randomness can be ground by reverting after seeing the hash
- Location: `smart-contracts/NextGenCore.sol` : `_mintProcessing`; `smart-contracts/RandomizerNXT.sol` : `calculateTokenHash`
- Mechanism: `_mintProcessing` calls `randomizer.calculateTokenHash` before `_safeMint`. For `NextGenRandomizerNXT`, this immediately writes `tokenToHash` using current-block values. A malicious ERC721 receiver can inspect `retrieveTokenHash(tokenId)` inside `onERC721Received` and revert if the hash is undesirable, reverting the whole mint and preserving funds/allowance for another attempt.
- Impact: An attacker can repeatedly retry mints until receiving favorable generative traits, breaking fair/random distribution for collections using `NextGenRandomizerNXT`.

## Expired or token-scoped delegations are treated as global active delegations
- Location: `smart-contracts/NFTdelegation.sol` : `retrieveGlobalStatusOfDelegation`; `smart-contracts/MinterContract.sol` : `mint` / `burnOrSwapExternalToMint`
- Mechanism: Delegation records store `expiryDate`, `allTokens`, and `tokens`, but `retrieveGlobalStatusOfDelegation` returns true solely when any record exists for the delegator/collection/delegate/use-case hash. The minter uses this function for authorization instead of checking expiry or token scope.
- Impact: An expired delegate can still consume a delegator’s allowlist mint rights and mint to an arbitrary `_mintTo`. For external burn/swap mints, a delegate authorized for only one token can be accepted as authorized for other owner tokens, allowing unauthorized burn/swap actions if the minter has transfer approval.

## Auction funds can be locked because the NFT is not escrowed
- Location: `smart-contracts/AuctionDemo.sol` : `participateToAuction` / `claimAuction` / `cancelBid`
- Mechanism: Bids are accepted without escrow of the NFT and without proving that `auctionDemo` is approved to transfer it. Settlement later calls `IERC721(gencore).safeTransferFrom(ownerOfToken, highestBidder, _tokenid)`. If the current token owner never approved the auction contract, revoked approval, transferred the NFT, or is otherwise unable to transfer, `claimAuction` reverts. After the auction end, bidders can no longer call `cancelBid` or `cancelAllBids`.
- Impact: A seller or token owner can make auction settlement impossible after bids are placed, permanently locking bidder ETH in the auction contract.

## Highest bids are non-binding until the auction ends
- Location: `smart-contracts/AuctionDemo.sol` : `cancelBid` / `cancelAllBids`
- Mechanism: Any active bidder, including the current highest bidder, can cancel and withdraw their bid at any time before `getAuctionEndTime`. There is no binding-bid period, escrow finality, or penalty for withdrawing the leading bid immediately before close.
- Impact: An attacker can place an artificially high bid to suppress competing bids, then cancel near the end of the auction, causing seller revenue loss or auction failure.

## Auction settlement finalizes even when ETH payments fail
- Location: `smart-contracts/AuctionDemo.sol` : `claimAuction`
- Mechanism: `claimAuction` sets `auctionClaim[_tokenid] = true`, transfers the NFT, and then sends ETH to the owner and refunds losing bidders using low-level `call`. The return values are only emitted in events; failures do not revert and there is no retry or withdrawal path for failed payments.
- Impact: If the seller or a refund recipient cannot receive ETH, settlement can complete while funds remain trapped in the auction contract permanently.

