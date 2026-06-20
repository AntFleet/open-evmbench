# Audit: 2023-10-nextgen

Add2, address _secondaryAdd3, uint256 _add1Percentage, uint256 _add2Percentage, uint256 _add3Percentage) public ArtistOrAdminRequired(_collectionID, this.proposeSecondaryAddressesAndPercentages.selector) {
        require (collectionArtistSecondaryAddresses[_collectionID].status == false, "Already approved");
        require (_add1Percentage + _add2Percentage + _add3Percentage == collectionRoyaltiesSecondarySplits[_collectionID].artistPercentage, "Check %");
    ```
    This is also correct.

    Let's inspect the `NextGenAdmins.sol` private mappings:
    `mapping (address => mapping (uint256 => bool)) private collectionAdmin;`
    `mapping (address => mapping (bytes4 => bool)) private functionAdmin;`
    Are there any issues with visibility or getters?
    They have public getters:
    `retrieveFunctionAdmin`, `retrieveCollectionAdmin`, etc.
    So they are fine.

    Wait! What about the `minter` address variable in `AuctionDemo.sol`?
    `IMinterContract public minter;`
    Is there any risk of a reentrancy or bid manipulation in `AuctionDemo.sol`?
    Let's check `participateToAuction`:
    ```solidity
    function participateToAuction(uint256 _tokenid) public payable {
        require(msg.value > returnHighestBid(_tokenid) && block.timestamp <= minter.getAuctionEndTime(_tokenid) && minter.getAuctionStatus(_tokenid) == true);
        auctionInfoStru memory newBid = auctionInfoStru(msg.sender, msg.value, true);
        auctionInfoData[_tokenid].push(newBid);
    }
    ```
    If `highestBidder` behaves maliciously (reverts on receiving ETH), we already showed that:
    1. During `claimAuction`:
       `(bool success, ) = payable(owner()).call{value: highestBid}("");`
       If the owner of the token is a contract that reverts, `claimAuction` reverts and winner can't claim? No, `owner()` is the `auctionDemo` owner (who is the contract deployer).
       Wait, `ownerOfToken` is the owner of the NFT.
       What about the failed refund of other bidders?
       `(bool success, ) = payable(auctionInfoData[_tokenid][i].bidder).call{value: auctionInfoData[_tokenid][i].bid}("");`
       And `success` is ignored.
       So even if a bidder reverts, the loop continues, and everyone else is refunded, and the winner gets the NFT. So there is no griefing DOS *unless* they exploit the `returnHighestBidder` bug or the reentrancy logic we found.

    Wait, what about `cancelBid` in `AuctionDemo.sol`?
    ```solidity
    function cancelBid(uint256 _tokenid, uint256 index) public {
        require(block.timestamp <= minter.getAuctionEndTime(_tokenid), "Auction ended");
        require(auctionInfoData[_tokenid][index].bidder == msg.sender && auctionInfoData[_tokenid][index].status == true);
        auctionInfoData[_tokenid][index].status = false;
        (bool success, ) = payable(auctionInfoData[_tokenid][index].bidder).call{value: auctionInfoData[_tokenid][index].bid}("");
        emit CancelBid(msg.sender, _tokenid, index, success, auctionInfoData[_tokenid][index].bid);
    }
    ```
    Wait, what if `success` is false?
    If the transfer of refund fails (e.g. the calling contract runs out of gas or rejects ether), `success` is false, but `status` is already set to `false`!
    This means the bidder’s active bid status is now `false`, but their money is trapped in the `auctionDemo` contract because the transfer failed!
    And since `status` is now `false`, they cannot call `cancelBid` again because it checks `auctionInfoData[_tokenid][index].status == true`.
    So their funds are permanently locked inside the contract with absolutely no way to retrieve them!
    Is there an owner-only withdraw function in `AuctionDemo.sol`?
    No! `AuctionDemo.sol` has *no* withdrawal function for trapped Ether!
    The only transfer of money to the owner is `payable(owner()).call{value: highestBid}` during `claimAuction`.
    This means if a user accidentally calls `cancelBid` from a smart contract wallet (like Gnosis Safe/Safe) that has a fallback reverting on plain transfers or consuming slightly more than default gas, their bid is canceled, their status is set to false, the transfer fails, and their entire bid is permanently trapped in the `AuctionDemo` contract forever.
    This is a significant loss of funds vulnerability (Low level transfer without verifying success or providing recovery).

    Let's write this down.
    **Short title**: Failed transfers in `cancelBid` and `cancelAllBids` permanently lock user funds
    **Location**: `AuctionDemo.sol` : `cancelBid` / `cancelAllBids`
    **Mechanism**: In both `cancelBid` and `cancelAllBids`, the bid status is set to `false` *before* the low-level ether call is executed. If the ether call fails (for instance, if the bidder is a contract that reverts on receiving ether, or because of gas exhaustion), the transaction does not revert (since the return value `success` is ignored and not validated with a `require` check). Because the status is now permanently set to `false`, the user cannot attempt to cancel or claim their bid again.
    **Impact**: Complete and irreversible loss of bidder funds, with the ether remaining trapped in the contract forever
