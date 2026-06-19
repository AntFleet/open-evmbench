# Audit: 2023-10-nextgen

## Denial of Service and Permanent Loss of Funds in Auction Claim
- Location: `AuctionDemo.sol` : `claimAuction`
- Mechanism: The `claimAuction` function sets `auctionClaim[_tokenid] = true` and then iterates through all bids to transfer the NFT to the winner and refund the losers using a push-over-push pattern. The external calls (`safeTransferFrom` and `call{value: ...}`) are not wrapped in try/catch blocks. If the highest bidder is a contract that reverts on `safeTransferFrom`, if the `owner()` reverts on receiving ETH, or if ANY losing bidder's address reverts on receiving their refund, the entire transaction reverts. Because `auctionClaim` is rolled back, the auction remains unclaimed. However, since the auction has ended, `cancelBid` and `cancelAllBids` can no longer be called.
- Impact: A single malicious or failing external call during the claim process will permanently brick the auction. The NFT remains with the seller, but all ETH from the losing bidders is permanently locked in the contract, resulting in a total loss of funds for the participants.

## Auction Proceeds Sent to Contract Owner Instead of NFT Seller
- Location: `AuctionDemo.sol` : `claimAuction`
- Mechanism: When an auction is successfully claimed, the NFT is transferred from the current owner (`ownerOfToken`) to the highest bidder. However, the highest bid amount (ETH) is sent to `owner()`, which is the deployer/admin of the `auctionDemo` contract (inherited from `Ownable`), rather than the `ownerOfToken` (the seller). 
- Impact: The seller of the NFT loses their asset and receives no compensation. The platform owner incorrectly receives all the auction proceeds, which is a critical logic error for any standard auction marketplace unless explicitly intended as a 100% platform fee (which is economically unviable for sellers).

## Circulation Supply Increments on Failed Mints/Burns
- Location: `NextGenCore.sol` : `mint`, `airDropTokens`, `burnToMint`
- Mechanism: In the `mint`, `airDropTokens`, and `burnToMint` functions, `collectionCirculationSupply` is incremented *before* checking if the new supply exceeds `collectionTotalSupply`. If the condition `collectionTotalSupply >= collectionCirculationSupply` evaluates to false, the function silently returns without minting the token (or burning the old one in `burnToMint`), but the `collectionCirculationSupply` remains permanently incremented.
- Impact: This breaks the invariant that `collectionCirculationSupply` accurately reflects the number of minted tokens. It will cause `totalSupplyOfCollection` to return incorrect values and could artificially inflate the perceived supply, potentially affecting downstream logic, metadata, or royalty calculations that rely on accurate supply counts.

## Weak and Predictable Randomness Source
- Location: `RandomizerNXT.sol` : `calculateTokenHash` and `XRandoms.sol` : `randomNumber` / `randomWord`
- Mechanism: The `NextGenRandomizerNXT` contract relies on `XRandoms` for randomness, which generates numbers using `block.prevrandao`, `blockhash(block.number - 1)`, and `block.timestamp`. These on-chain variables are entirely predictable and can be manipulated by validators/miners. Furthermore, `blockhash` is only valid for the last 256 blocks and returns `0` otherwise.
- Impact: An attacker or a malicious validator can predict or manipulate the generated randomness to mint NFTs with specific, desirable traits or hashes. This compromises the fairness and integrity of the generative art minting process, especially if certain traits hold significant market value.

## Potential Division by Zero in Price Calculation
- Location: `MinterContract.sol` : `getPrice`
- Mechanism: For `salesOption == 2` and `salesOption == 3`, the `getPrice` function calculates `tDiff` and `decreaserate` by dividing by `collectionPhases[_collectionId].timePeriod`. The `setCollectionCosts` function allows an admin to configure a collection with `timePeriod = 0` without any validation. If this occurs, any attempt to calculate the price during the active sale phases will result in a division by zero.
- Impact: If `timePeriod` is mistakenly set to 0, the minting process for that collection becomes completely bricked for the duration of the sale phases, as `getPrice` will always revert, preventing any user from minting and blocking the collection's launch.

## Missing Refund for Overpayment in Minting Functions
- Location: `MinterContract.sol` : `mint`, `burnOrSwapExternalToMint`
- Mechanism: The minting functions require `msg.value >= (getPrice(col) * _numberOfTokens)`. If a user sends more ETH than the exact required amount, the excess ETH is not refunded to the user. Instead, the entire `msg.value` is added to `collectionTotalAmount[col]`, which is later distributed as royalties to the artists and team via `payArtist`.
- Impact: Users who overpay (e.g., due to slippage tolerance, UI errors, or dynamic price changes between transaction submission and inclusion) will lose their excess funds. These funds are unfairly absorbed into the project's royalty pool instead of being returned to the buyer.
