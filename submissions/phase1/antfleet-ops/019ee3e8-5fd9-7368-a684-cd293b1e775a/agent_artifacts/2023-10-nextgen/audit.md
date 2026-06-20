# Audit: 2023-10-nextgen

## Unprotected function call
- Location: `MinterContract.sol` : `637` : `INextGenCore(gencore).airDropTokens(mintIndex, _recipient, _tokenData, _saltfun_o, _collectionID)`
- Mechanism: An unprotected function call is performed. The function `airDropTokens` can potentially re-enter the `mint` function.
- Impact: Reentrancy vulnerability. An attacker could drain Ether from this contract by causing the `airDropTokens` function to be called recursively.


## Unprotected function call
- Location: `MinterContract.sol` : `643` : `INextGenCore(gencore).mint(mintIndex, mintingAddress, _mintTo, tokData, _saltfun_o, col, phase)`
- Mechanism: An unprotected function call is performed. The function `mint` can potentially re-enter the `mint` function.
- Impact: Reentrancy vulnerability. An attacker could drain Ether from this contract by causing the `mint` function to be called recursively.


## Unprotected function call
- Location: `MinterContract.sol` : `690` : `gencore.mint(mintIndex, mintingAddress, ownerOfToken, tokData, _saltfun_o, col, phase)`
- Mechanism: An unprotected function call is performed. The function `mint` can potentially re-enter the `mint` function.
- Impact: Reentrancy vulnerability. An attacker could drain Ether from this contract by causing the `mint` function to be called recursively.


## Unprotected function call
- Location: `MinterContract.sol` : `701` : `INextGenCore(gencore).burnToMint(mintIndex, _burnCollectionID, _tokenId, _mintCollectionID, _saltfun_o, burner)`
- Mechanism: An unprotected function call is performed. The function `burnToMint` can potentially re-enter the `burnToMint` function.
- Impact: Reentrancy vulnerability. An attacker could drain Ether from this contract by causing the `burnToMint` function to be called recursively.


## Unprotected function call
- Location: `auctionDemo.sol` : `241` : `IERC721(gencore).safeTransferFrom(ownerOfToken, highestBidder, _tokenid)`
- Mechanism: An unprotected function call is performed. The function `safeTransferFrom` can potentially re-enter the `claimAuction` function.
- Impact: Reentrancy vulnerability. An attacker could drain Ether from this contract by causing the `safeTransferFrom` function to be called recursively.


## Unprotected function call
- Location: `auctionDemo.sol` : `248` : `(bool success, ) = payable(owner()).call{value: highestBid}("")`
- Mechanism: An unprotected function call is performed. The function `call` can potentially re-enter the `claimAuction` function.
- Impact: Reentrancy vulnerability. An attacker could drain Ether from this contract by causing the `call` function to be called recursively.


## Unprotected function call
- Location: `auctionDemo.sol` : `259` : `(bool success, ) = payable(auctionInfoData[_tokenid][i].bidder).call{value: auctionInfoData[_tokenid][i].bid}("")`
- Mechanism: An unprotected function call is performed. The function `call` can potentially re-enter the `claimAuction` function.
- Impact: Reentrancy vulnerability. An attacker could drain Ether from this contract by causing the `call` function to be called recursively.


## Unprotected function call
- Location: `auctionDemo.sol` : `266` : `(bool success, ) = payable(auctionInfoData[_tokenid][index].bidder).call{value: auctionInfoData[_tokenid][index].bid}("")`
- Mechanism: An unprotected function call is performed. The function `call` can potentially re-enter the `cancelBid` function.
- Impact: Reentrancy vulnerability. An attacker could drain Ether from this contract by causing the `call` function to be called recursively.


## Unprotected function call
- Location: `auctionDemo.sol` : `275` : `(bool success, ) = payable(auctionInfoData[_tokenid][i].bidder).call{value: auctionInfoData[_tokenid][i].bid}("")`
- Mechanism: An unprotected function call is performed. The function `call` can potentially re-enter the `cancelAllBids` function.
- Impact: Reentrancy vulnerability. An attacker could drain Ether from this contract by causing the `call` function to be called recursively.


## Unprotected function call
- Location: `NextGenCore.sol` : `531` : `gencoreContract.airDropTokens(mintIndex, _recipient, _tokenData, _saltfun_o, _collectionID)`
- Mechanism: An unprotected function call is performed. The function `airDropTokens` can potentially re-enter the `airDropTokens` function.
- Impact: Reentrancy vulnerability. An attacker could drain Ether from this contract by causing the `airDropTokens` function to be called recursively.


## Unprotected function call
- Location: `NextGenCore.sol` : `554` : `gencoreContract.mint(mintIndex, _mintingAddress, _mintTo, _tokenData, _saltfun_o, _collectionID, _phase)`
- Mechanism: An unprotected function call is performed. The function `mint` can potentially re-enter the `mint` function.
- Impact: Reentrancy vulnerability. An attacker could drain Ether from this contract by causing the `mint` function to be called recursively.


## Unprotected function call
- Location: `NextGenCore.sol` : `570` : `gencoreContract.burnToMint(mintIndex, _burnCollectionID, _tokenId, _mintCollectionID, _saltfun_o, burner)`
- Mechanism: An unprotected function call is performed. The function `burnToMint` can potentially re-enter the `burnToMint` function.
- Impact: Reentrancy vulnerability. An attacker could drain Ether from this contract by causing the `burnToMint` function to be called recursively.


## Prone to Front-Running Attack
- Location: `MinterContract.sol` : `655` : `gencoreContract.retrieveTokensMintedALPerAddress(col, _delegator)`
- Mechanism: The current block's timestamp (`block.timestamp`) and the current block number (`block.number`) are used to determine the timestamp and block number of the most recent mint, which an attacker could manipulate to get a recent mint first and thus gain an advantage.
- Impact: An attacker could drain Ether from this contract by manipulating the minting of a collection.


## Prone to Front-Running Attack
- Location: `MinterContract.sol` : `673` : `gencoreContract.retrieveTokensMintedPublicPerAddress(col, msg.sender)`
- Mechanism: The current block's timestamp (`block.timestamp`) and the current block number (`block.number`) are used to determine the timestamp and block number of the most recent mint, which an attacker could manipulate to get a recent mint first and thus gain an advantage.
- Impact: An attacker could drain Ether from this contract by manipulating the minting of a collection.


## Unprotected function call
- Location: `MinterContract.sol` : `675` : `(bool success, ) = payable(auctionInfoData[_tokenid][index].bidder).call{value: auctionInfoData[_tokenid][index].bid}("")
- Mechanism: An unprotected function call is performed. The function `call` can potentially re-enter the `cancelAllBids` function.
- Impact: Reentrancy vulnerability. An attacker could drain Ether from this contract by causing the `call` function to be called recursively.


## Unprotected function call
- Location: `auctionDemo.sol` : `294` : `(bool success, ) = payable(auctionInfoData[_tokenid][i].bidder).call{value: auctionInfoData[_tokenid][i].bid}("")`
- Mechanism: An unprotected function call is performed. The function `call` can potentially re-enter the `refund` function.
- Impact: Reentrancy vulnerability. An attacker could drain Ether from this contract by causing the `call` function to be called recursively.


## Unchecked transfer
- Location: `DelegationManagementContract.sol` : `184` : `uint256[] memory allDelegators = retrieveDelegators(msg.sender, _collectionAddress, USE_CASE_SUB_DELEGATION)`
- Mechanism: An `unchecked` operation can potentially lead to unintended behavior if an overflow occurs, which could result in write to an out of bounds index of a dynamic array or mapping.
- Impact: An attacker could potentially trigger unintended behavior, such as modifying or exposing sensitive data, by manipulating the array or mapping to be out of bounds.
