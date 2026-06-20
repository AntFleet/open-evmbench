# Audit: 2023-10-nextgen

Below are the genuine security vulnerabilities I found. (The two top-level directories `hardhat/smart-contracts/` and `smart-contracts/` are byte-identical copies, so each finding applies to both.)

## Incorrect highest-bidder selection in the auction
- Location: `AuctionDemo.sol` : `returnHighestBidder`
- Mechanism: The loop compares `auctionInfoData[_tokenid][i].bid > highBid`, but `highBid` is **never reassigned inside the loop** (it stays `0`). Consequently the condition is true for *every* active bid greater than zero, and `index` ends up pointing at the **last active bidder**, not the one with the maximum bid. Compare this with `returnHighestBid`, which correctly updates `highBid` and returns the true maximum. The two functions therefore disagree about who the winner is.
- Impact: `claimAuction` pays the contract owner the *correct* maximum amount (`returnHighestBid`) but transfers the NFT to the *wrong* address (`returnHighestBidder`). An attacker who simply places the chronologically last (small) active bid is treated as the winner and receives the token, while the genuine highest bidder is merely refunded. The `WinnerOrAdminRequired` modifier is also keyed off this wrong address, so the real top bidder cannot claim and the late low bidder can.

## claimAuction misallocates the NFT vs. the matched bid / silently swallows failed payouts
- Location: `AuctionDemo.sol` : `claimAuction`
- Mechanism: The function fetches `highestBid = returnHighestBid()` and `highestBidder = returnHighestBidder()` from two independently-computed functions (see bug above) and then looks for an entry where `bidder == highestBidder && bid == highestBid`. Because `returnHighestBidder` returns the last active bidder rather than the max bidder, the entry that matches `highestBid` may not belong to `highestBidder`, so the "winner" branch can simply never fire (no NFT transfer, no owner payment) while everyone — including the true winner — is sent down the "refund" branch. Additionally, all ETH transfers use low-level `call` whose `success` is captured but never `require`d, so refunds/payments to reverting recipients are silently dropped (the ETH stays trapped in the contract) and the auction is marked claimed regardless.
- Impact: Depending on bid ordering, the NFT seller may never be paid while the buyer keeps the token, or the token is never transferred at all even though the auction is permanently flagged `auctionClaim[_tokenid] = true`. Funds destined for a contract that rejects ETH are stranded in the auction contract with no recovery path.

## Predictable / miner-influenceable randomness for token hashes
- Location: `XRandoms.sol` : `randomNumber` / `randomWord`, consumed by `RandomizerNXT.sol` : `calculateTokenHash`
- Mechanism: `randomNumber()` and `randomWord()` derive their output from `keccak256(block.prevrandao, blockhash(block.number-1), block.timestamp)` — all values fully known at execution time. `RandomizerNXT.calculateTokenHash` mixes only these same public values plus `_mintIndex` to produce the token hash, and it is invoked **synchronously inside the mint transaction** (`NextGenCore._mintProcessing` → `randomizer.calculateTokenHash`).
- Impact: A minter calling through an attacker contract can compute the resulting token hash in the same transaction and `revert` whenever the outcome is undesirable, repeatedly retrying until a rare/high-value trait combination is produced. This defeats the fairness of the generative-art trait assignment (rarity grinding). Miners/validators can likewise bias outcomes.

## Unbounded loop in batched refund/cancel enables griefing and stuck claims
- Location: `AuctionDemo.sol` : `claimAuction`, `cancelAllBids`
- Mechanism: Both functions iterate over the entire `auctionInfoData[_tokenid]` array and perform an external `call` per active bid. `participateToAuction` has no minimum-increment and lets anyone push an unlimited number of bid entries (each only needs `msg.value > currentHighest`, which can be satisfied with dust-sized increments, or even many equal/lower entries since there is no per-bidder cap and `status` defaults active).
- Impact: An attacker can inflate the bids array for a token to a size where `claimAuction`/`cancelAllBids` exceed the block gas limit, permanently bricking settlement of that auction and locking all bidders' ETH (no per-bid withdrawal path other than the loop-based functions exists).

## `_mintProcessing` increments circulating supply even when the mint is skipped
- Location: `NextGenCore.sol` : `airDropTokens`, `mint`, `burnToMint`
- Mechanism: Each of these first does `collectionCirculationSupply += 1` and only *then* checks `if (collectionTotalSupply >= collectionCirculationSupply)` before actually minting. When the cap is reached the supply counter is still incremented but no token is minted, so `collectionCirculationSupply` can diverge above the number of tokens that actually exist.
- Impact: Because mint indices throughout `MinterContract` are computed as `viewTokensIndexMin + viewCirSupply`, an inflated circulation counter shifts subsequent mint indices past `reservedMaxTokensIndex`, and `setFinalSupply` / `totalSupplyOfCollection` report incorrect supply. The damage is bounded by the upstream index check in `MinterContract`, but any path that calls the core mint entrypoints with a stale/looser supply view (or future integrations) can corrupt the supply accounting and the index space.

---

Notes on items I deliberately did not report: the unchecked `call` returns in `MinterContract.payArtist`/`emergencyWithdraw` follow the same pattern as the auction and at worst strand funds rather than enabling theft; the ERC721/ERC2981/Math/MerkleProof files are stock OpenZeppelin and clean. The findings above are the ones with a concrete exploit path.

