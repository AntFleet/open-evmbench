# Audit: 2023-10-nextgen

The custom contracts appear twice in the prompt; the findings below apply to both mirrored copies.

## ERC721 receiver reentrancy bypasses mint caps and rate limits
- Location: `MinterContract.sol` : `mint`; `NextGenCore.sol` : `mint` / `_mintProcessing`
- Mechanism: `NextGenMinterContract.mint` checks wallet limits, then calls `gencore.mint(...)`. Inside `NextGenCore.mint`, `_mintProcessing` reaches `_safeMint(_mintTo, ...)`, which calls `onERC721Received` on a contract recipient before `tokensMintedAllowlistAddress` / `tokensMintedPerAddress` are incremented, and before `lastMintDate` is updated in `MinterContract.mint`. A malicious `_mintTo` contract can re-enter `mint` while those checks still see stale state.
- Impact: An attacker can recursively mint past allowlist/public-sale wallet caps and bypass the `salesOption == 3` one-mint-per-period throttle, potentially consuming the remaining collection supply in one transaction.

## Auction proceeds are paid to the auction contract owner, not the NFT seller
- Location: `AuctionDemo.sol` : `claimAuction`
- Mechanism: After transferring the NFT, the contract sends the winning bid to `payable(owner())`, where `owner()` is the `auctionDemo` contract owner, not the NFT owner returned by `IERC721(gencore).ownerOf(_tokenid)` and not the recipient originally minted in `mintAndAuction`.
- Impact: The auction contract owner captures all sale proceeds while the actual NFT owner receives nothing.

## Auction settlement can be permanently blocked because the NFT is never escrowed or approval-enforced
- Location: `AuctionDemo.sol` : `participateToAuction` / `claimAuction`; `MinterContract.sol` : `mintAndAuction`
- Mechanism: `mintAndAuction` mints the token to an external recipient, but the auction contract never escrows that NFT and never verifies approval before accepting bids. At settlement, `claimAuction` assumes it can execute `safeTransferFrom(ownerOfToken, highestBidder, _tokenid)`. If the current owner never approved the auction contract, moved the token, or the winner is a contract that rejects ERC721 receipts, settlement reverts after bidding has closed.
- Impact: The NFT and all non-cancelled bids can be locked indefinitely, with no post-expiry exit path for bidders.

## Function-admin rights are scoped only by selector, causing cross-contract privilege escalation
- Location: `NextGenAdmins.sol` : `registerFunctionAdmin` / `retrieveFunctionAdmin`
- Mechanism: Function-admin permissions are stored as `functionAdmin[address][bytes4 selector]`, with no contract address in the key. Multiple contracts expose identical signatures such as `updateCoreContract(address)`, `updateAdminContract(address)`, and `emergencyWithdraw()`, and each protected function checks only the selector.
- Impact: Granting an address limited rights for one contract silently grants the same rights on every contract sharing that selector, enabling unintended admin escalation across the system.

## Expired delegations and subdelegations remain valid indefinitely
- Location: `NFTdelegation.sol` : `retrieveGlobalStatusOfDelegation` / `registerDelegationAddressUsingSubDelegation` / `revokeDelegationAddressUsingSubdelegation`; `MinterContract.sol` : `mint` / `burnOrSwapExternalToMint`
- Mechanism: Delegation records store `expiryDate`, but `retrieveGlobalStatusOfDelegation` only checks whether a record exists, not whether it is still active. The subdelegation paths similarly authorize from historical delegation arrays rather than active unexpired records. The minter uses these stale checks to authorize delegated minting.
- Impact: A delegate or subdelegate keeps minting authority after expiry unless manually revoked, allowing continued use of someone else’s allowlist allocation or approved external NFT.

## The NXT randomizer allows free rerolls and trait grinding
- Location: `RandomizerNXT.sol` : `calculateTokenHash`; `NextGenCore.sol` : `_mintProcessing`; `XRandoms.sol` : `randomNumber` / `randomWord`
- Mechanism: `_mintProcessing` computes and stores the token hash before `_safeMint` invokes the receiver callback. Under the NXT path, the hash is derived synchronously from current block values and written immediately. A receiving contract can read the just-written hash during `onERC721Received`, evaluate the resulting traits, and revert if the outcome is undesirable.
- Impact: An attacker can repeatedly reroll at gas cost until a favorable token hash appears, breaking rarity fairness for collections using this randomizer.

## Cancelled-bid spam can gas-DoS auction settlement
- Location: `AuctionDemo.sol` : `participateToAuction` / `cancelBid` / `cancelAllBids` / `claimAuction` / `returnHighestBid` / `returnHighestBidder`
- Mechanism: Every bid is appended permanently to `auctionInfoData[_tokenid]`; cancellation only flips `status` to `false`. Settlement and bid-discovery functions iterate over the full historical array. Because fully cancelled histories drop the active highest bid back to zero, an attacker can repeatedly place and cancel cheap bids, growing the array with minimal net cost.
- Impact: An attacker can inflate a single auction’s history until `claimAuction` becomes too expensive to execute, permanently preventing settlement and trapping active funds.

