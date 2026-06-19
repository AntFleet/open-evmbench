# Audit: 2023-10-nextgen

## Reentrant Mint Bypasses Mint Limits
- Location: `smart-contracts/MinterContract.sol` : `mint`; `smart-contracts/NextGenCore.sol` : `mint` / `_mintProcessing`
- Mechanism: `NextGenMinterContract.mint` calls `gencore.mint` before finalizing sale accounting, and `NextGenCore.mint` updates per-address mint counters only after `_safeMint`. `_safeMint` calls `onERC721Received` on contract recipients, allowing a recipient contract to reenter `mint` before `tokensMintedPerAddress`, `tokensMintedAllowlistAddress`, and sale option 3 `lastMintDate` reflect the in-progress mint.
- Impact: A contract minter can mint more than its public or allowlist allocation and can bypass the sale option 3 “1 mint/period” restriction by recursively minting during the ERC721 receiver callback.

## Auctioned NFTs Are Not Escrowed
- Location: `smart-contracts/AuctionDemo.sol` : `participateToAuction` / `claimAuction`
- Mechanism: Bids are accepted without transferring or locking the NFT in the auction contract. At claim time, the contract fetches `ownerOf(_tokenid)` and tries to `safeTransferFrom` the current owner to the winner. The token owner can transfer, burn, or revoke approval before the auction ends, while bidders can no longer cancel after the end time.
- Impact: A token owner can make the auction unclaimable after receiving bids, permanently locking bidder funds in the auction contract. If the token is transferred to a new owner who has approved the auction contract, the auction can also transfer that new owner’s token to the winner even though they were not the seller.

## Delegation Expiry And Token Scope Are Ignored
- Location: `smart-contracts/MinterContract.sol` : `mint` / `burnOrSwapExternalToMint`; `smart-contracts/NFTdelegation.sol` : `retrieveGlobalStatusOfDelegation`
- Mechanism: The minter authorizes delegated actions using `retrieveGlobalStatusOfDelegation`, which only checks whether any delegation record exists. It does not check `expiryDate`, whether the delegation is active at `block.timestamp`, or whether the delegation was limited to a specific token via `allTokens == false` and `tokens`.
- Impact: An expired or token-scoped delegate remains authorized indefinitely as a collection-wide delegate. They can consume a delegator’s allowlist mint allowance and, where the minter has token approval, force external burn/swap flows for tokens beyond the delegated scope.

## Failed ETH Payments Are Treated As Successful Accounting
- Location: `smart-contracts/MinterContract.sol` : `payArtist`; `smart-contracts/AuctionDemo.sol` : `claimAuction`, `cancelBid`, `cancelAllBids`
- Mechanism: The contracts use low-level `.call{value: ...}("")` for payouts and refunds but do not revert or preserve retryable balances when `success == false`. `payArtist` zeroes `collectionTotalAmount` before sending payments; auction cancellation marks bids inactive before refunding; auction claim marks the auction claimed while ignored refund or seller-payment failures can leave ETH in the contract.
- Impact: Artist proceeds, team proceeds, bidder refunds, or auction proceeds can become permanently stuck while internal accounting says they were paid or no longer owed. In the minter, those stranded funds can later be swept through `emergencyWithdraw`.

## Insecure Block-Based Randomness
- Location: `smart-contracts/RandomizerNXT.sol` : `calculateTokenHash`; `smart-contracts/XRandoms.sol` : `randomNumber` / `randomWord`
- Mechanism: `NextGenRandomizerNXT` derives token hashes from `blockhash(block.number - 1)`, `block.timestamp`, `block.prevrandao` via `XRandoms`, and an external `randoms` contract. The hash is generated synchronously during mint, using values that are predictable or biasable by block proposers/builders and by whoever controls the configured random source.
- Impact: Token hash assignment can be biased for collections using this randomizer. A block producer or compromised/configured random source can influence rarity or trait outcomes.

