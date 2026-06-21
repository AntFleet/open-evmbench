# Audit: 2023-10-nextgen

## Sales option 3 mint-rate limit bypass
- Location: hardhat/smart-contracts/MinterContract.sol : mint
- Mechanism: For `salesOption == 3`, the per-period throttle compares `block.timestamp` against `lastMintDate`, but `lastMintDate` is not set to the actual last mint time. It is derived as `allowlistStartTime + (timePeriod * (circulatingSupply - 1))`, which advances by only one nominal period per mint regardless of when mints occur. After the first period elapses, an attacker can submit many consecutive `mint` calls in the same block (or same day); each call sees a stale `lastMintDate` while `tDiff` stays ≥ 1, so the `"1 mint/period"` guard never binds to real elapsed time.
- Impact: An attacker can mint far more than one token per configured period, draining supply early, distorting the Dutch-auction pricing curve, and undermining the intended scarcity/timing economics of sales option 3.

## Expired delegations still authorize minting
- Location: hardhat/smart-contracts/MinterContract.sol : mint / burnOrSwapExternalToMint
- Mechanism: Allowlist and external-burn mint paths gate delegated callers through `DelegationManagementContract.retrieveGlobalStatusOfDelegation`, which only checks whether `globalDelegationHashes[hash].length > 0`. It never compares `expiryDate` to `block.timestamp`, and the minter never calls `retrieveActiveDelegators` or similar expiry-aware helpers. Delegations therefore remain valid forever until explicitly revoked, even after their intended expiration.
- Impact: A hot wallet that was only supposed to mint until a given date can continue minting or burning/minting on behalf of the cold-wallet owner indefinitely, violating the delegation trust model and potentially exhausting allowlist allocation or burning delegated NFTs without ongoing owner consent.

## Token-scoped delegations are not enforced
- Location: hardhat/smart-contracts/MinterContract.sol : mint / burnOrSwapExternalToMint
- Mechanism: `DelegationManagementContract` supports per-token delegations (`allTokens == false` with a specific `_tokenId`), and exposes `retrieveTokenStatus` for that purpose. The minter never uses it. It only calls `retrieveGlobalStatusOfDelegation`, which returns true if any delegation record exists for the `(delegator, collection, delegate, useCase)` tuple, ignoring both expiry and whether the delegation was scoped to a single token.
- Impact: A delegate granted rights only over one external NFT (or a narrowly scoped allowlist delegation) can act as if they had collection-wide delegation, minting on the full allowlist allocation or burning/minting with NFTs outside the delegated token scope.

## Predictable and manipulable on-chain randomness (RandomizerNXT)
- Location: hardhat/smart-contracts/RandomizerNXT.sol : calculateTokenHash
- Mechanism: `NextGenRandomizerNXT.calculateTokenHash` derives token hashes from `blockhash(block.number - 1)`, plus `randomPool.randomNumber()` and `randomPool.randomWord()`, which are themselves computed from `block.prevrandao`, `blockhash(block.number - 1)`, and `block.timestamp`. The user-supplied `_saltfun_o` argument is ignored. All inputs are visible or influenceable by block producers/searchers at mint time.
- Impact: A miner/validator or sophisticated MEV actor can precompute or bias token hashes before minting, selectively minting or ordering transactions to obtain desirable generative outputs, breaking fairness of the random art assignment.

## Circulation-supply accounting race can brick remaining mints
- Location: hardhat/smart-contracts/NextGenCore.sol : mint / airDropTokens / burnToMint
- Mechanism: `collectionCirculationSupply` is incremented before the supply guard, and if `collectionTotalSupply < collectionCirculationSupply` the function skips `_mintProcessing` without rolling back the increment. The minter’s pre-check reads `viewCirSupply()` once per transaction; concurrent last-slot mints can both pass the minter check, while only one core mint succeeds. The loser still permanently inflates `collectionCirculationSupply`.
- Impact: An attacker racing legitimate minters at collection sellout can inflate circulation without minting, causing subsequent mints to fail at the core layer and effectively reducing or permanently blocking the remaining mintable supply (denial of service / supply griefing).

## Auction settlement ignores failed ETH transfers
- Location: hardhat/smart-contracts/AuctionDemo.sol : claimAuction
- Mechanism: During `claimAuction`, ETH is sent to the NFT owner and to losing bidders via low-level `call`, but return values are not required to succeed. The function sets `auctionClaim[_tokenid] = true` up front and continues even when `success == false`. A recipient contract with a reverting `receive`/`fallback` therefore does not block settlement.
- Impact: The winning bidder can still receive the NFT via `safeTransferFrom` while losing bidders (or even the protocol owner) never receive their refunds or sale proceeds. Those funds remain trapped in `auctionDemo` with no generic withdraw path for bidders, causing direct fund loss and enabling griefing via rejecting-contract bids.

## Underpriced multi-mint payment for sales option 3
- Location: hardhat/smart-contracts/MinterContract.sol : mint
- Mechanism: Payment is validated once up front as `msg.value >= getPrice(col) * _numberOfTokens`, using the price at the start of the transaction. The mint loop then calls `gencore.mint` repeatedly, increasing circulating supply each iteration while `getPrice` for sales option 3 is designed to rise with supply (`collectionMintCost + (collectionMintCost / rate) * supply`). The single upfront price snapshot does not track the rising per-token price inside the loop.
- Impact: Although `_numberOfTokens == 1` is enforced for sales option 3 at the end of the function (so multi-mint in one tx reverts), any code path or future change that permits `_numberOfTokens > 1`, or the same pattern applied elsewhere, would let minters pay below the true cumulative price and extract value from the collection/artists. The flawed ordering also shows the economic guard is not enforced coherently with supply-based pricing.

## `returnHighestBidder` uses incorrect comparison state
- Location: hardhat/smart-contracts/AuctionDemo.sol : returnHighestBidder
- Mechanism: In the loop over `auctionInfoData`, the function compares `bid > highBid` and updates `index`, but never assigns `highBid = auctionInfoData[_tokenid][i].bid`. Because `highBid` remains zero, `index` ends up pointing to the last active bid with any positive amount, not necessarily the numerically highest bid. This happens to align with the true highest bidder only while bids are strictly increasing and never decrease after partial cancellations in ways that break index monotonicity.
- Impact: If auction rules change, cancellations interact unexpectedly, or bids are ever ingested out of strict increasing order, `returnHighestBidder` can identify the wrong winner. `claimAuction` would then transfer the NFT and pay sale proceeds to an incorrect address while refunding the true highest bidder as a loser, causing wrongful asset transfer and loss of bidder funds.

## `payArtist` rounding leaves recoverable dust and uses caller-chosen team splits
- Location: hardhat/smart-contracts/MinterContract.sol : payArtist
- Mechanism: Royalty distribution uses integer division on each slice (`royalties * percentage / 100`) without reconciling remainder wei, and the admin-supplied `_teamperc1` / `_teamperc2` parameters are only constrained to sum with the artist percentage to 100 at payout time, not against the previously configured `collectionRoyaltiesPrimarySplits.teamPercentage`. The function zeroes `collectionTotalAmount` before transfers complete.
- Impact: Repeated payouts can strand ETH dust in the minter contract; a privileged admin can redirect the team portion of primary-sale proceeds to arbitrary addresses at settlement time, diverting funds from the intended team recipients while still passing the superficial 100% check.

## Permissionless `updateUseCaseCounter` expands delegation surface
- Location: hardhat/smart-contracts/NFTdelegation.sol : updateUseCaseCounter
- Mechanism: `updateUseCaseCounter` has no access control and increments `useCaseCounter`, which bounds valid `_useCase` values in `registerDelegationAddress`. Any external account can therefore expand the set of registrable use cases at will.
- Impact: While not directly stealing funds, an attacker can register delegations under newly created use-case IDs that downstream integrators may not expect or filter, potentially granting hot-wallet permissions on novel use cases before off-chain systems or dependent contracts recognize and restrict them.

