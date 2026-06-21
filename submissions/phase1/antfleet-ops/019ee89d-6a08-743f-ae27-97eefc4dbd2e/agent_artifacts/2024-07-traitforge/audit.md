# Audit: 2024-07-traitforge

## Predictable entropy enables cherry-picked minting of rare/powerful tokens
- Location: contracts/EntropyGenerator/EntropyGenerator.sol : getNextEntropy / getPublicEntropy / deriveTokenParameters (and contracts/TraitForgeNft/TraitForgeNft.sol : _mintInternal)
- Mechanism: `getNextEntropy()` returns entropy deterministically by walking `currentSlotIndex`/`currentNumberIndex`, which advance by exactly one per regular mint (`_mintInternal` is its only caller, once per `mintToken`/`mintWithBudget` mint). The entropy for any `(slot, number)` — and its derived `isForger`, `forgePotential`, `nukeFactor`, including the special `999999` "golden god" — is fully readable in advance through the `public view` functions `getPublicEntropy` and `deriveTokenParameters`. The current consumption index equals the count of prior `_mintInternal` calls, which is observable on-chain (e.g., `Minted` events / `tokenEntropy` history). An attacker computes the upcoming index, previews the exact token they would receive, and mints only when it is valuable, otherwise waiting or letting others burn the junk slots.
- Impact: An attacker reliably mints the rarest/strongest NFTs (max nuke factor, golden god) and skips bad ones, breaking fair distribution and enabling outsized NukeFund claims and airdrop allocations.

## Minting is not bounded by `maxGeneration`, inflating total supply
- Location: contracts/TraitForgeNft/TraitForgeNft.sol : _incrementGeneration / _mintInternal
- Mechanism: `_incrementGeneration()` only checks `generationMintCounts[currentGeneration] >= maxTokensPerGen` and then unconditionally does `currentGeneration++`; neither it nor `mintToken`/`mintWithBudget` ever enforces `currentGeneration <= maxGeneration`. (By contrast, `forge()` does enforce `newGeneration <= maxGeneration`.) Once a generation fills, the next mint rolls the generation forward without any upper bound, so minting continues past generation 10 indefinitely.
- Impact: The intended hard cap of 10 generations × 10,000 tokens is bypassed, allowing unbounded supply inflation that dilutes every value/airdrop/fund mechanic keyed to scarcity.

## DAOFund swaps with zero slippage protection (sandwichable)
- Location: contracts/DAOFund/DAOFund.sol : receive()
- Mechanism: On every ETH inflow `receive()` calls `swapExactETHForTokens{value: msg.value}(0, path, address(this), block.timestamp)` with `amountOutMin = 0` and a `block.timestamp` deadline. This performs an at-market buy of `token` with no minimum-output bound and no meaningful deadline, so any inflow (e.g., the DAO share routed from `NukeFund.receive`) is a fully sandwichable swap.
- Impact: MEV searchers sandwich each buy-and-burn, extracting protocol value that should have been used to burn tokens, with loss bounded only by available liquidity.

## `NukeFund.receive` reverts on any failed downstream send, bricking all fee inflows
- Location: contracts/NukeFund/NukeFund.sol : receive()
- Mechanism: When `airdropStarted() && daoFundAllowed()`, `receive()` executes `daoAddress.call{value: devShare}('')` then `require(success, 'ETH send failed')`. If `daoAddress` is the in-scope `DAOFund`, its `receive()` performs a Uniswap swap plus a `Trait` burn that can revert (no liquidity, zero output, or `Trait` paused — `Trait` is `ERC20Pausable`), making `success == false` and reverting `NukeFund.receive`. Because `TraitForgeNft._distributeFunds`, `EntityForging.forgeWithListed`, and `EntityTrading.buyNFT` all push ETH into `NukeFund.receive`, any such revert propagates upward. (The `!airdropStarted` branch has the same coupling to `DevFund`/owner.)
- Impact: A paused `Trait` token or a failing DAO swap causes a protocol-wide denial of service on minting, forging, and trading.

## `mintWithBudget` gates on the global token counter instead of the per-generation count
- Location: contracts/TraitForgeNft/TraitForgeNft.sol : mintWithBudget
- Mechanism: The loop condition is `while (budgetLeft >= mintPrice && _tokenIds < maxTokensPerGen)`, but `_tokenIds` is the global cumulative counter (incremented by `_mintNewEntity` forges as well), not `generationMintCounts[currentGeneration]`. Once total tokens (mints + forges) reach `maxTokensPerGen` (10,000), the loop body never runs and the function simply refunds the whole budget forever.
- Impact: `mintWithBudget` becomes permanently unusable after 10,000 total tokens and, before that, mis-bounds minting against global supply rather than the per-generation cap.

## Burning misattributes the airdrop deduction to the original minter
- Location: contracts/TraitForgeNft/TraitForgeNft.sol : burn (and contracts/Airdrop/Airdrop.sol : subUserAmount)
- Mechanism: Before the airdrop starts, `burn()` calls `airdropContract.subUserAmount(initialOwners[tokenId], entropy)`, decrementing the *original minter's* `userInfo` and the global `totalValue` regardless of who currently owns or burns the token. Anyone who acquires and burns a token (or nukes it via `NukeFund.nuke`, which calls `burn`) reduces a third party's airdrop allocation; since `Airdrop.claim` computes `totalTokenAmount * userInfo / totalValue`, shrinking `totalValue` simultaneously inflates every remaining claimer's payout.
- Impact: Attackers can grief minters by erasing their airdrop allocations and skew airdrop shares in their own favor by destroying other holders' tokens.

## `initializeAlphaIndices` is owner-gated but must be invoked by the NFT contract on every generation rollover
- Location: contracts/EntropyGenerator/EntropyGenerator.sol : initializeAlphaIndices (called by contracts/TraitForgeNft/TraitForgeNft.sol : _incrementGeneration)
- Mechanism: `initializeAlphaIndices()` carries the `onlyOwner` modifier, yet `_incrementGeneration()` calls `entropyGenerator.initializeAlphaIndices()` on each generation increment. The EntropyGenerator constructor registers `TraitForgeNft` only as `allowedCaller`, not as owner (owner stays the deployer), so the call's `msg.sender` (TraitForgeNft) fails the `onlyOwner` check and reverts, reverting the increment and the mint/forge that triggered it.
- Impact: Under the deployment implied by the code, every mint/forge that fills a generation reverts, permanently preventing generation advancement (and thus most minting) unless ownership is hand-transferred to the NFT contract.

## Off-by-one in forge-potential checks allows one extra forge
- Location: contracts/EntityForging/EntityForging.sol : listForForging / forgeWithListed
- Mechanism: The limit checks use `<=`: `listForForging` requires `forgingCounts[tokenId] <= forgePotential`, and `forgeWithListed` increments then requires `forgingCounts[mergerTokenId] <= mergerForgePotential`. Because the forger's count is checked at list time (when it may equal `forgePotential`) and only incremented during forging, a forger can be re-listed and forged when its count already equals `forgePotential`, yielding `forgePotential + 1` total forges.
- Impact: Tokens exceed their intended forge limit by one, producing extra offspring/generations beyond the designed cap.

## Overpayment in `forgeWithListed` is permanently locked
- Location: contracts/EntityForging/EntityForging.sol : forgeWithListed
- Mechanism: The function requires `msg.value >= forgingFee` but distributes exactly `forgingFee` (`devFee` to NukeFund + `forgerShare` to the forger owner). Any `msg.value - forgingFee` remains in the contract, which exposes no withdrawal or sweep function.
- Impact: ETH paid above the listing fee is irrecoverably trapped in the contract.

