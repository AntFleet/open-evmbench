# Audit: 2024-07-traitforge

## Approved operators can steal nuke payouts
- Location: `contracts/NukeFund/NukeFund.sol` : `nuke`
- Mechanism: `nuke()` authorizes `nftContract.isApprovedOrOwner(msg.sender, tokenId)`, which includes approved operators, then pays `claimAmount` to `msg.sender`. It does not require `msg.sender` to be the NFT owner and does not pay `ownerOf(tokenId)`.
- Impact: Any approved operator for a user’s NFT can burn that NFT through `NukeFund` and receive the entire nuke payout, stealing the owner’s claim and destroying their token.

## Entropy is predictable and manipulable
- Location: `contracts/EntropyGenerator/EntropyGenerator.sol` : `writeEntropyBatch1`, `writeEntropyBatch2`, `writeEntropyBatch3`, `getNextEntropy`; `contracts/TraitForgeNft/TraitForgeNft.sol` : `_mintInternal`
- Mechanism: Entropy values are generated from `keccak256(abi.encodePacked(block.number, i))`, written by public batch functions, exposed through `getPublicEntropy`, and consumed sequentially by minting. The next NFT attributes are therefore knowable before minting, and batch initialization can be front-run or timed by anyone.
- Impact: Attackers can choose when to initialize or mint so they receive high-value entropy tokens, including better nuke factors, forge roles, and airdrop weights. This lets them unfairly extract value from the NFT economy, airdrop allocation, and NukeFund.

## DAO fund swaps can be sandwiched to drain value
- Location: `contracts/DAOFund/DAOFund.sol` : `receive`
- Mechanism: Incoming ETH is swapped with `swapExactETHForTokens` using `amountOutMin = 0`. There is no slippage protection, oracle check, or bounded minimum output before burning the received tokens.
- Impact: MEV attackers can sandwich any ETH sent to the DAO fund, manipulate the pool price, and cause the contract to buy very few tokens while the attacker captures the ETH value through the round trip trade.

## Public minting bypasses the max generation cap
- Location: `contracts/TraitForgeNft/TraitForgeNft.sol` : `_mintInternal`, `_incrementGeneration`
- Mechanism: `forge()` enforces `newGeneration <= maxGeneration`, but normal minting does not. `_incrementGeneration()` simply increments `currentGeneration` once `maxTokensPerGen` is reached and never checks `currentGeneration < maxGeneration`.
- Impact: Attackers can continue minting generations beyond the configured `maxGeneration`, inflating NFT supply and creating additional entropy, airdrop weight, and potential NukeFund claimants beyond the intended cap.

## Forger tokens can be used one time over their forge limit
- Location: `contracts/EntityForging/EntityForging.sol` : `listForForging`, `forgeWithListed`
- Mechanism: `listForForging()` allows listing when `forgingCounts[tokenId] <= forgePotential`, so a token already at its limit can still be listed. `forgeWithListed()` then increments the forger count but never re-checks it against `forgePotential`.
- Impact: A forger NFT can be used `forgePotential + 1` times instead of the intended maximum, creating extra forged NFTs and diluting the intended scarcity/limit mechanics.

