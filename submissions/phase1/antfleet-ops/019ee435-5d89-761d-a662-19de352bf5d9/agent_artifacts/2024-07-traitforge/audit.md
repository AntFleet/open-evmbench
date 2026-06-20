# Audit: 2024-07-traitforge

## Predictable entropy allows mint cherry-picking

- Location: `contracts/EntropyGenerator/EntropyGenerator.sol` : `writeEntropyBatch1`, `writeEntropyBatch2`, `writeEntropyBatch3`, `getNextEntropy`; `contracts/TraitForgeNft/TraitForgeNft.sol` : `_mintInternal`
- Mechanism: NFT entropy is generated from prefilled `entropySlots`, but those slots are written by public functions using only `block.number` and the loop index. The resulting entropy stream is deterministic and publicly queryable through `getPublicEntropy`; the next consumed position is also inferable from mint progression. A minter can simulate or monitor upcoming entropy values and mint only when the next value gives favorable properties such as high nuke factor, forger status, high forge potential, or the special `999999` value.
- Impact: Attackers can acquire disproportionately valuable NFTs at the normal mint price, bias airdrop weight, obtain favorable forging roles, and later extract outsized value from `NukeFund`, damaging the protocol economy.

## Approved operators can steal nuke proceeds

- Location: `contracts/NukeFund/NukeFund.sol` : `nuke`
- Mechanism: `nuke()` authorizes any address passing `nftContract.isApprovedOrOwner(msg.sender, tokenId)`, but pays the ETH claim to `msg.sender` instead of the token owner. If an NFT owner has approved `NukeFund` to burn the token and also has an approved operator, for example a marketplace operator, that operator can call `nuke()` first. The burn succeeds because `NukeFund` is approved, while the payout goes to the operator.
- Impact: An approved operator can burn a victim’s mature NFT and steal the entire nuke payout from the fund.

## Minting bypasses max generation cap

- Location: `contracts/TraitForgeNft/TraitForgeNft.sol` : `_mintInternal`, `_incrementGeneration`
- Mechanism: `forge()` enforces `newGeneration <= maxGeneration`, but the public mint path does not. When `generationMintCounts[currentGeneration] >= maxTokensPerGen`, `_mintInternal()` calls `_incrementGeneration()`, and `_incrementGeneration()` blindly increments `currentGeneration` without checking `maxGeneration`.
- Impact: After the configured final generation fills, any user can continue minting generation `maxGeneration + 1` and beyond, inflating supply and breaking generation-based scarcity and economics.

## DAOFund swaps are sandwichable with zero slippage protection

- Location: `contracts/DAOFund/DAOFund.sol` : `receive`
- Mechanism: Every ETH receipt triggers `swapExactETHForTokens` with `amountOutMin` set to `0`. There is no oracle check, TWAP, or caller-provided minimum output. A MEV searcher can front-run a transaction that sends ETH to `DAOFund`, manipulate the TRAIT/WETH pool price, let `DAOFund` buy at the manipulated price, and back-run to restore the pool.
- Impact: ETH intended for DAO buy-and-burn can be extracted by sandwich attacks, causing the DAO to receive and burn far fewer TRAIT tokens than expected.

## Listed forgers get one extra forge beyond their limit

- Location: `contracts/EntityForging/EntityForging.sol` : `listForForging`, `forgeWithListed`
- Mechanism: `listForForging()` allows a token to be listed when `forgingCounts[tokenId] <= forgePotential`. `forgeWithListed()` then increments the forger’s count but never checks the post-increment value against `forgePotential`. Therefore, a forger with `forgingCounts == forgePotential` can still be listed and used once more.
- Impact: Forger NFTs can exceed their intended forge limit by one per reset period, creating extra child NFTs and bypassing the intended scarcity constraint.

