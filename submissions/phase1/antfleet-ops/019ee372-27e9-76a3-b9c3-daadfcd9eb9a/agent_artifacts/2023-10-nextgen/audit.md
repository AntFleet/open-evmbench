# Audit: 2023-10-nextgen

## Denial of Service in `claimAuction` due to unbounded array iteration
- Location: `hardhat/smart-contracts/AuctionDemo.sol` : `claimAuction`
- Mechanism: The `claimAuction` function processes auction resolution by iterating over the unbounded `auctionInfoData` array, executing an external ETH transfer (`call{value: ...}`) for every uncancelled bid. A malicious actor can easily inflate this array by repeatedly placing negligible bids (e.g., in increments of 1 wei). Since processing each refund costs gas, a large enough array will predictably cause the `for` loop to exceed the Ethereum block gas limit. 
- Impact: Once the auction ends, `cancelBid` becomes uncallable (due to the `block.timestamp <= minter.getAuctionEndTime` constraint). As a result, the out-of-gas condition in `claimAuction` will persistently prevent resolution, permanently locking up the requested NFT along with all ETH funds locked by honest participants within the contract.
