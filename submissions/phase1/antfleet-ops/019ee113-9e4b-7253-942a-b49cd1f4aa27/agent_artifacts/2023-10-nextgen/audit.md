# Audit: 2023-10-nextgen

## AuctionDemo: returnHighestBidder returns incorrect winner
- Location: `AuctionDemo.sol` : `returnHighestBidder`
- Mechanism: The loop condition `if (auctionInfoData[_tokenid][i].bid > highBid && ...status == true)` updates `index = i` but never updates `highBid` (`highBid` remains 0). As a result, the function matches every active bid with `bid > 0`, leaving `index` pointing to the **last** such bid in the array, not the one with the maximum value. In `claimAuction`, the winning bid is identified by `bidder == highestBidder && bid == highestBid`. When the wrong bidder is returned, neither the true highest bidder nor the false "winner" satisfies both conditions, so the NFT is never transferred and the highest bidder is silently refunded while the seller receives nothing.
- Impact: Auctions can complete with no winner and no payment to the seller, even though a valid higher bid exists. The true highest bidder loses their bid amount (refunded) and the seller keeps the NFT but receives no proceeds.

## AuctionDemo: Reentrancy in cancelBid and cancelAllBids
- Location: `AuctionDemo.sol` : `cancelBid`, `cancelAllBids`
- Mechanism: Both functions set `auctionInfoData[_tokenid][index].status = false` before making the external call `payable(bidder).call{value: bid}("")`. A malicious contract bidder can re-enter `cancelBid` (or `cancelAllBids`) from its `receive`/`fallback` function. Because the status update occurs before the external call, the re-entered call will see the bid as still active (or cancel another active bid) and trigger another refund, draining contract ETH.
- Impact: An attacker can drain all ETH held by the auction contract by placing multiple bids from a contract and re-entering on refund.

## AuctionDemo: DoS in returnHighestBidder when no bids exist
- Location: `AuctionDemo.sol` : `returnHighestBidder`
- Mechanism: The function declares `uint256 index;` (uninitialized) and unconditionally executes `auctionInfoData[_tokenid][index].status` at the end. If `auctionInfoData[_tokenid].length == 0`, this reverts with an array out-of-bounds error rather than the intended `revert("No Active Bidder")`. The `WinnerOrAdminRequired` modifier calls `returnHighestBidder`, so `claimAuction` becomes uncallable (DoS) for tokens that never received any bids.
- Impact: `claimAuction` cannot be called for auctioned tokens with zero bids, permanently locking the ability to distribute the NFT.

## MinterContract: payArtist loses ETH on failed transfers
- Location: `MinterContract.sol` : `payArtist`
- Mechanism: The function sets `collectionTotalAmount[_collectionID] = 0` before making five raw `.call{value: ...}("")` transfers to artist/team addresses. Each call's `success` return value is only used in event emission; the function never reverts on failure. If any recipient is a contract that reverts (or is blacklisted), the corresponding ETH stays in the minter contract while accounting shows the balance as zero.
- Impact: ETH can become permanently stuck in the contract. Additionally, integer division (`royalties * percentage / 100`) can leave rounding dust that is never distributed.

## NextGenCore: State desync in mint/airDropTokens
- Location: `NextGenCore.sol` : `mint`, `airDropTokens`
- Mechanism: Both functions unconditionally increment `collectionAdditionalData[_collectionID].collectionCirculationSupply` **before** checking `if (collectionTotalSupply >= collectionCirculationSupply)`. If the supply is already at maximum, the increment still occurs, desynchronizing the accounting. Subsequent legitimate mints will see an inflated circulation supply and fail the check even when there is remaining supply.
- Impact: An attacker (or buggy admin) can permanently block future mints by triggering calls when supply is exhausted, leaving the collection unable to mint even if supply is later expanded.

## RandomizerNXT/XRandoms: Weak on-chain randomness
- Location: `RandomizerNXT.sol` : `calculateTokenHash`, `XRandoms.sol` : `randomNumber`/`randomWord`
- Mechanism: Both contracts derive randomness from `blockhash(block.number - 1)`, `block.prevrandao`, and `block.timestamp`. These values are either known to miners in advance or predictable by observers of the mempool. The resulting token hash in `tokenToHash` can be computed before the transaction is mined.
- Impact: If any feature depends on the resulting token hash (e.g., revealing rarity, gated mints, or airdrop selection), miners or sophisticated attackers can manipulate or predict outcomes.

## MinterContract: setCollectionCosts can be changed during active sale
- Location: `MinterContract.sol` : `setCollectionCosts`
- Mechanism: There is no check that the sale is not active or that no mints have occurred. A collection admin (or compromised function admin) can call `setCollectionCosts` at any time, including mid-sale, changing `collectionMintCost`, `collectionEndMintCost`, `rate`, `timePeriod`, `salesOption`, and `delAddress`.
- Impact: An admin can change mint prices (including to zero or to astronomical values) or switch the delegation collection used for allowlist verification during an ongoing sale, enabling theft or griefing.

## MinterContract: Front-running bypass for sales option 3 period check
- Location: `MinterContract.sol` : `mint` (salesOption == 3 branch)
- Mechanism: The "1 mint/period" check uses `lastMintDate[col]` and updates it only **after** the mint loop and external calls complete. Two concurrent transactions in the same period can both read the same `lastMintDate`, both pass `require(tDiff >= 1 ...)`, and both succeed before either writes the new timestamp.
- Impact: An attacker can mint multiple tokens in the same period for a Dutch-auction-style sale, breaking the intended time-based scarcity mechanism.

## NextGenCore: setFinalSupply permanently locks collection size
- Location: `NextGenCore.sol` : `setFinalSupply`
- Mechanism: Any function admin can call this after the public sale ends plus `setFinalSupplyTimeAfterMint`. It sets `collectionTotalSupply = collectionCirculationSupply` and recomputes `reservedMaxTokensIndex`. There is no way to reverse this. If called prematurely (e.g., before all airdrops or burn-to-mints are processed), it permanently caps the collection below its intended size.
- Impact: Permanent reduction of collection supply, blocking planned future mints or burn-to-mints and potentially stranding reserved tokens.

## RandomizerNXT: _saltfun_o parameter ignored
- Location: `RandomizerNXT.sol` : `calculateTokenHash`
- Mechanism: The function accepts a `_saltfun_o` parameter but never uses it in the hash calculation: `keccak256(abi.encodePacked(_mintIndex, blockhash(block.number - 1), randoms.randomNumber(), randoms.randomWord()))`.
- Impact: Users/contracts expecting the salt to influence the resulting token hash (e.g., for provably fair distribution or commitment schemes) will be misled, reducing the effective entropy of the hash and potentially causing collisions if `_mintIndex` collides with a previous mint.
