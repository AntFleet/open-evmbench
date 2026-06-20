# Audit: 2023-10-nextgen

## Reentrant mint bypasses wallet and cadence limits
- Location: `smart-contracts/MinterContract.sol` : `mint`; `smart-contracts/NextGenCore.sol` : `mint`
- Mechanism: `NextGenMinterContract.mint` checks allowlist/public mint limits before calling `gencore.mint`, but `NextGenCore.mint` only increments `tokensMintedAllowlistAddress` / `tokensMintedPerAddress` after `_mintProcessing`, and `_mintProcessing` uses `_safeMint`, which calls `onERC721Received` on contract recipients. A malicious recipient can reenter `mint` from that callback while its minted count and `lastMintDate` have not yet been updated.
- Impact: A contract minter can mint beyond allowlist allowance, public per-wallet allowance, and the `salesOption == 3` one-mint-per-period rule, draining more supply than intended.

## NXT randomizer output can be biased and ground
- Location: `smart-contracts/RandomizerNXT.sol` : `calculateTokenHash`; `smart-contracts/XRandoms.sol` : `randomNumber` / `randomWord`; `smart-contracts/NextGenCore.sol` : `_mintProcessing`
- Mechanism: The NXT randomizer derives token hashes from block variables and `XRandoms`, which itself uses `block.prevrandao`, `blockhash`, and `block.timestamp`. This is not a secure randomness source against block producers. In addition, `_mintProcessing` sets the hash before `_safeMint` calls the recipient hook, so a malicious recipient can inspect the hash during `onERC721Received` and revert unfavorable mints.
- Impact: Validators/proposers can bias rarity, and contract minters can repeatedly revert bad mints until receiving a favorable token hash.

## Expired or token-scoped delegations authorize global mint actions
- Location: `smart-contracts/NFTdelegation.sol` : `retrieveGlobalStatusOfDelegation`; `smart-contracts/MinterContract.sol` : `mint`, `burnOrSwapExternalToMint`
- Mechanism: `retrieveGlobalStatusOfDelegation` returns true whenever any delegation record exists for the hash; it does not check `expiryDate`, `allTokens`, or token-specific scope. The minter uses this getter as full authorization for allowlist delegated minting and external burn/swap minting.
- Impact: An address with an expired delegation, or a delegation intended for only one token, can still act as a valid delegate. This can consume a delegator’s allowlist allocation or force burn/swap flows for approved external NFTs.

## Expired subdelegations remain powerful
- Location: `smart-contracts/NFTdelegation.sol` : `registerDelegationAddressUsingSubDelegation`, `revokeDelegationAddressUsingSubdelegation`
- Mechanism: Subdelegation authorization is checked by scanning `retrieveDelegators`, which returns historical delegator entries and does not validate expiry or token scope. A subdelegation grant that has expired still appears in that list.
- Impact: A former subdelegate can continue registering or revoking delegations on behalf of the delegator after the intended expiry.

## Auction settlement can permanently lock bidder funds
- Location: `smart-contracts/AuctionDemo.sol` : `claimAuction`
- Mechanism: The auction never escrows the NFT and only attempts `safeTransferFrom(ownerOfToken, highestBidder, tokenId)` at claim time. If the current token owner has not approved the auction contract, transferred the token, or the winning bidder is a contract that rejects ERC721 receipt, `claimAuction` reverts. Bidders cannot cancel after the auction end.
- Impact: A seller or malicious highest bidder can make settlement impossible, locking all active bids in the auction contract.

## Auction claim is gas-DoSable with stale bid entries
- Location: `smart-contracts/AuctionDemo.sol` : `participateToAuction`, `cancelBid`, `cancelAllBids`, `claimAuction`
- Mechanism: Every bid is appended to `auctionInfoData`, and canceled bids remain in the array forever. `returnHighestBid`, `returnHighestBidder`, and especially `claimAuction` iterate over the entire array. An attacker can create many bids and cancel them before the end, leaving a large inactive history.
- Impact: Settlement can exceed the block gas limit, preventing the NFT transfer and refunds from ever completing.

## Winning bidder can reenter and refund its own bid at the end timestamp
- Location: `smart-contracts/AuctionDemo.sol` : `claimAuction`, `cancelBid`
- Mechanism: `claimAuction` sets `auctionClaim` but does not mark the winning bid inactive before calling `safeTransferFrom` to the winner. If the winner is a contract, its `onERC721Received` hook can reenter `cancelBid` when `block.timestamp == auctionEndTime`, because `claimAuction` allows `>= end` and `cancelBid` allows `<= end`.
- Impact: The winner can receive the NFT and reclaim the winning bid. The subsequent owner payment may fail or be paid using other bidders’ funds.

## Failed ETH transfers clear accounting anyway
- Location: `smart-contracts/MinterContract.sol` : `payArtist`; `smart-contracts/AuctionDemo.sol` : `claimAuction`
- Mechanism: Both contracts use low-level `.call{value: ...}("")` and only emit the returned `success` flag. `payArtist` zeroes `collectionTotalAmount` before making payouts, and `claimAuction` marks the auction claimed before paying the owner and refunding bidders. Failed transfers do not revert and there is no retry accounting.
- Impact: Artist/team payouts, auction proceeds, or bidder refunds can fail silently while the contract records the obligation as completed, leaving funds stuck or later withdrawable through unrelated emergency paths.

