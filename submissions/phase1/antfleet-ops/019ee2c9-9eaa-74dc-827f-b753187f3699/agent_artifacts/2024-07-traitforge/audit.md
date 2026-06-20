# Audit: 2024-07-traitforge

## Approved operators can steal nuke payouts by burning someone else’s NFT
- Location: [NukeFund.sol](/Users/augstar/open-evmbench/audit_sources/2024-07-traitforge/contracts/NukeFund/NukeFund.sol:153) : `nuke`
- Mechanism: `nuke()` accepts any caller for whom `nftContract.isApprovedOrOwner(msg.sender, tokenId)` is true, but it pays the ETH reward to `msg.sender` rather than to `ownerOf(tokenId)`. If the real owner has approved `NukeFund` for the token and also has any separate approved operator for that NFT, that operator can call `nuke()`, satisfy both approval checks, cause [TraitForgeNft.sol](/Users/augstar/open-evmbench/audit_sources/2024-07-traitforge/contracts/TraitForgeNft/TraitForgeNft.sol:141) `burn()` to destroy the user’s NFT, and receive the claim themselves.
- Impact: Any approved third party can front-run the real owner, burn the victim’s token, and steal the full nuke payout.

## Entropy is fully predictable and partially user-controllable
- Location: [EntropyGenerator.sol](/Users/augstar/open-evmbench/audit_sources/2024-07-traitforge/contracts/EntropyGenerator/EntropyGenerator.sol:47) : `writeEntropyBatch1`/`writeEntropyBatch2`/`writeEntropyBatch3`/`getPublicEntropy`; [TraitForgeNft.sol](/Users/augstar/open-evmbench/audit_sources/2024-07-traitforge/contracts/TraitForgeNft/TraitForgeNft.sol:280) : `_mintInternal`
- Mechanism: The entropy table is filled by public functions using only `keccak256(block.number, i)`, so whoever triggers each batch can choose the block that fixes future traits. After that, `getPublicEntropy()` exposes the generated values, and minting consumes them in a fixed sequence via `getNextEntropy()`. Because token IDs and mint counts are public, users can infer the next slot/index and know the exact entropy, forger status, forge potential, and nuke factor of upcoming mints before sending a mint transaction.
- Impact: Attackers can snipe only favorable NFTs, skip bad mints, front-run desirable upcoming traits, and even bias the initial entropy table by being the party that initializes the batches.

## Forger listings bypass the intended forge cap by one
- Location: [EntityForging.sol](/Users/augstar/open-evmbench/audit_sources/2024-07-traitforge/contracts/EntityForging/EntityForging.sol:67) : `listForForging`; [EntityForging.sol](/Users/augstar/open-evmbench/audit_sources/2024-07-traitforge/contracts/EntityForging/EntityForging.sol:102) : `forgeWithListed`
- Mechanism: A forger can be listed while `forgingCounts[tokenId] <= forgePotential`, and `forgeWithListed()` then increments `forgingCounts[forgerTokenId]` without re-checking the cap. That means a token already exactly at its limit can still be listed once more and used for one extra forge before future listings fail.
- Impact: Forger owners can mint one more child than their entropy-imposed cap and collect one extra forging fee per reset period, inflating supply and breaking the scarcity/economic rules.

## DAO funding swaps are sandwichable because they accept any output amount
- Location: [DAOFund.sol](/Users/augstar/open-evmbench/audit_sources/2024-07-traitforge/contracts/DAOFund/DAOFund.sol:16) : `receive`
- Mechanism: Every ETH deposit immediately executes `swapExactETHForTokens` with `amountOutMin = 0`, then burns whatever tokens arrive. With no slippage bound or oracle check, a searcher can front-run the buy to move the pool price against `DAOFund`, let `DAOFund` buy at an arbitrarily bad rate, then back-run to restore the price and capture the value difference.
- Impact: MEV searchers can siphon a large fraction of protocol ETH routed into `DAOFund`, leaving the DAO with far fewer burned tokens than intended.

Assumption: I excluded owner-only parameter abuse and pure deployment/misconfiguration issues unless they created a concrete non-owner exploit path.

