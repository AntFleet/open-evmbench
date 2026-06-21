# Audit: 2023-10-nextgen
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

### Predictable / grindable on-chain randomness in RandomizerNXT
*(consensus, 6 of 6 reports)*
- Location: `RandomizerNXT.sol` : `calculateTokenHash`; `XRandoms.sol` : `randomNumber` / `randomWord` (seed written in `NextGenCore.sol` : `_mintProcessing` before `_safeMint`)
- Mechanism: The token hash is `keccak256(_mintIndex, blockhash(block.number-1), randoms.randomNumber(), randoms.randomWord())`, and `randomNumber`/`randomWord` derive solely from `block.prevrandao`, `blockhash(block.number-1)` and `block.timestamp` — all readable and constant within the mint transaction; `_mintIndex` is deterministic. The hash is assigned synchronously before the `onERC721Received` callback, so a contract recipient can read `retrieveTokenHash(_mintIndex)` and revert when the outcome is unfavorable, re-rolling across blocks. Block proposers can additionally bias `prevrandao`/`timestamp`.
- Impact: Trait/rarity grinding and full predictability of the generative seed for any collection using `RandomizerNXT`; a sophisticated minter or builder mints only rare outputs. (VRF/RNG randomizers are unaffected.)

### Mint reentrancy bypasses per-wallet / allowlist / per-period caps
*(consensus, 5 of 6 reports)*
- Location: `NextGenCore.sol` : `mint` / `_mintProcessing`; `MinterContract.sol` : `mint`
- Mechanism: `NextGenCore.mint` increments `tokensMintedPerAddress` / `tokensMintedAllowlistAddress` only *after* `_mintProcessing` → `_safeMint` → `onERC721Received` on the caller-controlled `_mintTo`; `MinterContract.mint` has no reentrancy guard and checks the cap only on entry; for `salesOption == 3` `lastMintDate` is updated only after the loop. A malicious `_mintTo` re-enters `mint` during the callback with stale counters, so the `<= viewMaxAllowance` / `tDiff >= 1` checks pass again. The same callback-before-state-update pattern exists in `airDropTokens`, `burnToMint`, and `burnOrSwapExternalToMint`.
- Impact: A single address exceeds `maxCollectionPurchases` (public) / `_maxAllowance` (allowlist) and the salesOption-3 one-mint-per-period rule, letting one actor sweep a drop and defeat fair distribution.
- Reviewer disagreement: opus shot 3 explicitly defended this path, asserting `mint` follows checks-effects-interactions (state incremented before external value transfers).

### Delegation expiry ignored in mint / burn-swap authorization
*(consensus, 4 of 6 reports)*
- Location: `NFTdelegation.sol` : `retrieveGlobalStatusOfDelegation`; `MinterContract.sol` : `mint` (allowlist branch) and `burnOrSwapExternalToMint`
- Mechanism: `retrieveGlobalStatusOfDelegation` returns true whenever any delegation record exists for the delegator/delegate/use-case tuple and never inspects the stored `expiryDate`. The minter uses this boolean as the allowlist-delegation gate and as the authorization gate for delegated external burn/swap. (gpt-5.5 shot 3 adds that sub-delegation checks likewise rely on historical delegator lists rather than active, unexpired state.)
- Impact: An expired delegation keeps authorizing the delegate to consume the delegator's allowlist allocation (minting to an arbitrary `_mintTo`) and to drive the burn/swap flow until an explicit `revokeDelegationAddress`; an authorization-freshness gap.

### claimAuction reentrancy via never-invalidated bid status
*(consensus, 3 of 6 reports)*
- Location: `AuctionDemo.sol` : `claimAuction` interacting with `cancelBid` / `cancelAllBids`
- Mechanism: `claimAuction` sets `auctionClaim[_tokenid] = true` but never sets the individual bids' `status = false`, and has no reentrancy guard. It makes external calls with stale `status == true` state — `safeTransferFrom` (→ `onERC721Received` on the winner) then `.call` refunds to losers. `claimAuction` requires `timestamp >= getAuctionEndTime` while `cancelBid`/`cancelAllBids` require `timestamp <= getAuctionEndTime`; both hold when `timestamp == getAuctionEndTime` (proposer-influenceable). A bidder-contract re-enters `cancelBid` for a still-`true` bid and is paid a second time; the `auctionClaim` guard blocks re-entering `claimAuction` but not `cancelBid`.
- Impact: The winner takes the NFT and claws back its winning bid (so `owner()` receives nothing), or any bidder double-withdraws its deposit. All bids share one ETH balance, so the shortfall is covered by other auctions' deposits — theft of escrowed funds.

### claimAuction unchecked ETH transfers strand funds
*(consensus, 3 of 6 reports)*
- Location: `AuctionDemo.sol` : `claimAuction`
- Mechanism: `claimAuction` transfers the NFT to the winner, then pays `owner()` / refunds losers via low-level `call`, only emitting `success` without requiring it and with no revert or recovery path (`auctionClaim` is already set). gpt-5.5 shots 2/3: the seller payout to `owner()` can silently fail, leaving the winner with the NFT and the seller unpaid. opus shot 3: a losing bidder whose refund `.call` fails has its funds permanently stranded.
- Impact: NFT delivered while the seller is never paid; failed refunds permanently strand bidder ETH with no post-end recovery path.

### updateUseCaseCounter has no access control
*(consensus, 3 of 6 reports)*
- Location: `NFTdelegation.sol` (`DelegationManagementContract`) : `updateUseCaseCounter`
- Mechanism: `function updateUseCaseCounter() public { useCaseCounter = useCaseCounter + 1; }` is callable by anyone and mutates global protocol state; `registerDelegationAddress` only validates `_useCase > 0 && _useCase <= useCaseCounter`.
- Impact: Any account can arbitrarily and repeatedly raise `useCaseCounter`, widening the set of registerable use cases. It cannot forge reserved `998`/`999` or affect existing delegations, so severity is low — but it is a genuine unguarded mutation of shared state.

### setCollectionCosts admits values that brick pricing / minting
*(consensus, 2 of 6 reports)*
- Location: `MinterContract.sol` : `setCollectionCosts` (consumed by `getPrice`, `mint`, `mintAndAuction`)
- Mechanism: The setter performs no validation. With `_timePeriod == 0`, `salesOption 2` `getPrice` computes `(block.timestamp - allowlistStartTime) / timePeriod` and `salesOption 3` `mint` computes `(block.timestamp - timeOfLastMint) / timePeriod` — both divide-by-zero and revert. (opus shot 3 adds: `salesOption 2` with `_collectionEndMintCost > _collectionMintCost` makes `getPrice` compute `collectionMintCost - collectionEndMintCost`, which underflows and reverts under 0.8.x checked arithmetic.)
- Impact: A collection admin can configure a phase that makes `getPrice` (and every `mint`/`burnToMint`/`burnOrSwapExternalToMint`/`mintAndAuction` path that calls it) revert, permanently bricking that collection's minting until reconfigured. Requires admin privilege; an unrecoverable foot-gun with no guard.

### payArtist zeroes accounting then makes unchecked transfers
*(consensus, 2 of 6 reports)*
- Location: `MinterContract.sol` : `payArtist`
- Mechanism: `payArtist` sets `collectionTotalAmount[_collectionID] = 0` and then performs five `payable(...).call{value:...}("")` transfers whose `success` is emitted but never required, with no retry. A reverting payee's share stays in the contract while the per-collection accounting is already zeroed. Because all collections share one balance and `emergencyWithdraw` drains it without resetting `collectionTotalAmount`, accounting and actual balance can drift, so a later `payArtist` can also silently fail yet mark the collection paid.
- Impact: A single reverting payee permanently locks that collection's primary-sale proceeds; royalty distribution breaks; funds are recoverable only via privileged emergency withdrawal.
- Reviewer disagreement: opus shots 1/2 characterized `payArtist` as CEI-correct and admin-gated (addressing reentrancy, not the failed-payout fund-locking scenario).

### Token-scoped delegations treated as collection-wide authority
*(consensus, 2 of 6 reports)*
- Location: `MinterContract.sol` : `burnOrSwapExternalToMint` (and `mint` allowlist branch); `NFTdelegation.sol` : `retrieveGlobalStatusOfDelegation`
- Mechanism: `retrieveGlobalStatusOfDelegation` returns true for any delegation record between owner and delegate without checking `allTokens` or matching the delegated `tokens` field against `_tokenId`.
- Impact: A delegate authorized for only one token can burn/swap any eligible token the delegator owns in the configured external ID range (given the owner approved the minter); a token-scoped delegation is escalated to collection-wide burn/swap authority.

---

## Minority findings

### External burn/swap tokens reusable if returned
*(minority, 1 of 6 reports)*
- Location: `MinterContract.sol` : `burnOrSwapExternalToMint`
- Mechanism: The function validates the external token range and transfers the token to `burnOrSwapAddress`, but never records that `(_erc721Collection, _burnCollectionID, _tokenId)` has already been used. If the configured address is a swap/escrow rather than an irrecoverable burn address, the same external token can be returned and used again.
- Impact: A user who regains the external NFT can repeatedly mint from the same qualifying token, paying only the mint price each time, breaking one-external-token-for-one-mint accounting and draining supply.

### External burn allowlist proofs not collection-bound
*(minority, 1 of 6 reports)*
- Location: `MinterContract.sol` : `burnOrSwapExternalToMint` (allowlist branch)
- Mechanism: The Merkle leaf is `keccak256(abi.encodePacked(_tokenId, tokData))`; it omits `_erc721Collection`, `_burnCollectionID`, `_mintCollectionID`, and the token owner, so proof validity is tied only to token ID and token data.
- Impact: If multiple external burn/swap collections are initialized for the same mint collection, an owner of a cheaper or unintended NFT with the same token ID can reuse a proof intended for another collection and mint.

### Cancelable high bids allow last-moment auction price suppression
*(minority, 1 of 6 reports)*
- Location: `AuctionDemo.sol` : `participateToAuction`, `cancelBid`, `cancelAllBids`, `claimAuction`
- Mechanism: Bids — including the current highest — remain freely cancelable while `block.timestamp <= auctionEndTime`. An attacker places/controls a low bid, submits a much higher bid from another address to suppress competitors, then cancels the high bid immediately before close; the low bid remains the highest active bid and claims.
- Impact: The attacker wins at an artificially low price or griefs the auction by withdrawing the bid others had to beat. Requires control of multiple bidding addresses and timing before close.

### payArtist lets executor redirect team proceeds
*(minority, 1 of 6 reports)* *(conflicting reviews: 3 of 6 reports characterized payArtist as CEI-correct / admin-gated)*
- Location: `MinterContract.sol` : `payArtist`
- Mechanism: `payArtist` accepts `_team1`, `_team2`, `_teamperc1`, `_teamperc2` from the caller and only checks `artistPercentage + _teamperc1 + _teamperc2 == 100`; the stored `teamPercentage` and any configured team recipients are not enforced.
- Impact: Any account granted the `payArtist` function-admin role can redirect the entire team share of a collection's primary-sale proceeds to arbitrary addresses, including itself. The artist share stays constrained, but the team portion is caller-controlled.
- Reviewer disagreement: opus shots 1/2/3 treated `payArtist` as CEI-correct / admin-gated and did not flag the caller-supplied team parameters.

### Auction griefing DoS via unbounded auctionInfoData growth
*(minority, 1 of 6 reports)*
- Location: `AuctionDemo.sol` : `participateToAuction`, `returnHighestBid`, `returnHighestBidder`, `claimAuction`
- Mechanism: `participateToAuction` pushes a struct to `auctionInfoData[_tokenid]` and the array is never compacted (`cancelBid` only flips `status`). Because `participateToAuction` requires only `msg.value > returnHighestBid` (the current *active* high), an attacker repeatedly bids 1 wei above the active high and immediately `cancelBid`s to reclaim it, appending one permanent entry per iteration at ~no capital cost. `returnHighestBid`, `returnHighestBidder`, and `claimAuction` all loop the full array on-chain.
- Impact: Once the array is large enough, `returnHighestBid` (called inside `participateToAuction`) and `claimAuction` exceed the block gas limit and revert permanently — the auction can no longer accept bids or be settled, stranding any winner's funds and the NFT. Cost to the attacker is only gas (cheap on L2s).

---

*Reconciliation: 14 distinct findings across the six input reports (by code path + root cause); 14 findings emitted — 9 consensus, 5 minority. No finding dropped.*

