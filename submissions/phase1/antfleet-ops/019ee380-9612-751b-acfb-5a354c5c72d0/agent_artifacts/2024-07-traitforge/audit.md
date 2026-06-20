# Audit: 2024-07-traitforge

I audited the TraitForge protocol contracts. Below are the genuine security vulnerabilities I found.

## Approved operator can nuke a token and steal the payout
- Location: contracts/NukeFund/NukeFund.sol : `nuke`
- Mechanism: `nuke` gates on `nftContract.isApprovedOrOwner(msg.sender, tokenId)` and an approval check (`getApproved == this || isApprovedForAll(msg.sender, this)`), but it sends the ETH payout to `msg.sender` (`payable(msg.sender).call{ value: claimAmount }`) rather than to the token owner. Any address that the owner approved — a single-token approval or, worse, an `isApprovedForAll` operator such as a marketplace contract — satisfies `isApprovedOrOwner`. Such an operator can call `nuke`, burning the owner's NFT and redirecting the entire claim amount to itself.
- Impact: A malicious or compromised operator (or anyone the owner ever granted blanket `setApprovalForAll` to for trading/forging) can burn victims' NFTs and drain up to 50% of the fund per token straight into their own wallet, with zero consent from the owner at nuke time.

## Fully predictable / pre-computable entropy
- Location: contracts/EntropyGenerator/EntropyGenerator.sol : `writeEntropyBatch1/2/3`, `getNextEntropy`, `initializeAlphaIndices`
- Mechanism: Entropy slots are filled with `uint256(keccak256(abi.encodePacked(block.number, i)))` at batch-write time and are then read deterministically by `getNextEntropy` (a public, monotonic `currentSlotIndex/currentNumberIndex` cursor). Every future entropy value, and the "golden" `999999` slot selected by `initializeAlphaIndices` (derived from `blockhash` + `block.timestamp`), is computable by anyone reading the chain before they mint.
- Impact: An attacker can compute exactly which entropy the next mint will receive and selectively mint/skip to grab forger tokens (`entropy % 3 == 0`), maximum forge potential, maximum nuke factor (`entropy / 40`), or the golden `999999` slot — defeating the intended randomness of token attributes and the nuke economy.

## `mintWithBudget` uses the global token counter as a per-generation cap
- Location: contracts/TraitForgeNft/TraitForgeNft.sol : `mintWithBudget`
- Mechanism: The loop condition is `while (budgetLeft >= mintPrice && _tokenIds < maxTokensPerGen)`. `_tokenIds` is the global, ever-increasing token id counter, not the per-generation count (`generationMintCounts[currentGeneration]`). Once total minted tokens reach `maxTokensPerGen` (10000) — which happens at the end of generation 1 — the condition is permanently false.
- Impact: `mintWithBudget` silently stops minting and refunds the entire budget for every caller from generation 2 onward, permanently breaking the batch-mint path; it also caps lifetime batch minting to 10000 tokens regardless of how many generations exist.

## Minting can exceed `maxGeneration`
- Location: contracts/TraitForgeNft/TraitForgeNft.sol : `_mintInternal` / `_incrementGeneration`
- Mechanism: `_mintInternal` calls `_incrementGeneration()` whenever the current generation fills, and `_incrementGeneration` bumps `currentGeneration` with no check against `maxGeneration`. The `forge` path enforces `newGeneration <= maxGeneration`, but the primary mint path does not.
- Impact: After generation 10 fills, normal minting rolls over into generation 11, 12, … indefinitely, violating the protocol's generation cap and the pricing/economic assumptions tied to it.

## `startAirdrop` pulls tokens from `tx.origin`
- Location: contracts/Airdrop/Airdrop.sol : `startAirdrop`
- Mechanism: `traitToken.transferFrom(tx.origin, address(this), amount)` sources the airdrop funding from `tx.origin` instead of `msg.sender`. The function is reached via `TraitForgeNft.startAirdrop` (owner-only), so the actual token spender is whatever EOA originated the transaction, and the approval must come from `tx.origin`.
- Impact: Use of `tx.origin` for value transfer is a phishing-prone anti-pattern: if the owner EOA has approved the Airdrop contract and is induced to originate a transaction that reaches this path, the tokens are pulled from the EOA rather than the intended account; it also breaks composability with any contract-based owner (multisig), which can never be `tx.origin`.

## Unbounded slippage in DAOFund swap
- Location: contracts/DAOFund/DAOFund.sol : `receive`
- Mechanism: The auto-swap calls `swapExactETHForTokens(0, path, address(this), block.timestamp)` with `amountOutMin = 0`. Any ETH forwarded to the DAOFund is market-bought with zero slippage protection and then immediately burned.
- Impact: A searcher can sandwich every incoming swap, extracting value from the protocol's buy-and-burn flow on each deposit; the burn receives far fewer tokens than fair value.

## Forging-limit off-by-one
- Location: contracts/EntityForging/EntityForging.sol : `listForForging`
- Mechanism: The potential check is `forgingCounts[tokenId] <= forgePotential`. Since `forgingCounts` starts at 0 and is incremented once per successful forge, allowing equality lets a token be listed and forged `forgePotential + 1` times (e.g. potential 5 permits forges at counts 0,1,2,3,4,5).
- Impact: Every forger/merger entity can forge one more time than its entropy-derived limit, inflating the number of offspring beyond design.

