# Audit: 2024-07-traitforge

I found 6 genuine vulnerabilities.

## Approved operators can steal nuke payouts
- Location: `contracts/NukeFund/NukeFund.sol` : `nuke`
- Mechanism: `nuke()` authorizes `nftContract.isApprovedOrOwner(msg.sender, tokenId)` but sends the ETH payout to `msg.sender`, not to the actual NFT owner. If an owner has approved `NukeFund` for the token and has also granted an operator approval to another address, that operator can call `nuke()` first, burn the owner’s NFT, and receive the full claim amount.
- Impact: Approved marketplace/operator addresses can steal nuke proceeds and destroy users’ NFTs.

## NFT entropy is predictable and can be sniped
- Location: `contracts/EntropyGenerator/EntropyGenerator.sol` : `getNextEntropy`, `getPublicEntropy`; `contracts/TraitForgeNft/TraitForgeNft.sol` : `_mintInternal`
- Mechanism: Entropy is precomputed into public slots, exposed through `getPublicEntropy`, consumed sequentially by `getNextEntropy`, and also emitted through `EntropyRetrieved`. The current index is inferable from mint count/events/storage, so users can know upcoming token traits before minting, including nuke factor, forger status, forge potential, and the special `999999` entropy position.
- Impact: Attackers can selectively mint only valuable NFTs, snipe high nuke-factor or high-forge-potential tokens, avoid bad entropy, and extract value from the minting, forging, and nuke-fund economies.

## Anyone can initialize the entropy table
- Location: `contracts/EntropyGenerator/EntropyGenerator.sol` : `writeEntropyBatch1`, `writeEntropyBatch2`, `writeEntropyBatch3`
- Mechanism: The batch entropy writers are public and have no `onlyOwner` or allowed-caller restriction. The first caller permanently fills large portions of the entropy table using `keccak256(block.number, i)`, so any account can initialize protocol randomness before the intended operator and choose timing or block inclusion conditions.
- Impact: Attackers can front-run initialization, bias or grief the NFT trait distribution, and permanently control when the deterministic entropy set is created.

## Public minting bypasses the max generation cap
- Location: `contracts/TraitForgeNft/TraitForgeNft.sol` : `_mintInternal`, `_incrementGeneration`
- Mechanism: Forging enforces `newGeneration <= maxGeneration`, but normal minting does not. When the current generation reaches `maxTokensPerGen`, `_mintInternal()` calls `_incrementGeneration()`, and `_incrementGeneration()` increments `currentGeneration` without checking `maxGeneration`.
- Impact: Users can continue minting generations beyond the configured `maxGeneration`, breaking the intended supply/generation cap and diluting rarity/economic assumptions.

## Forgers can exceed their forge limit by one use
- Location: `contracts/EntityForging/EntityForging.sol` : `listForForging`, `forgeWithListed`
- Mechanism: `listForForging()` allows listing when `forgingCounts[tokenId] <= forgePotential`. During `forgeWithListed()`, the forger’s count is incremented, but there is no post-increment check for the forger side. A forger with count equal to its potential can still list and successfully forge once more.
- Impact: Each forger NFT can be used `forgePotential + 1` times per reset period, creating extra child NFTs beyond the intended limit.

## DAO fund swaps have zero slippage protection
- Location: `contracts/DAOFund/DAOFund.sol` : `receive`
- Mechanism: Incoming ETH is swapped through Uniswap with `amountOutMin = 0`. Any public contribution can be sandwiched or price-manipulated, forcing the contract to accept arbitrarily poor execution before burning the received tokens.
- Impact: MEV/searcher attackers can extract most of the ETH value from DAO-fund contributions, causing the protocol to burn far fewer tokens than intended.

