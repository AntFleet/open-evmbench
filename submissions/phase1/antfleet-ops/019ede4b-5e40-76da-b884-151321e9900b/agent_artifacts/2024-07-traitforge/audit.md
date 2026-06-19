# Audit: 2024-07-traitforge

## Airdrop: `tx.origin` usage breaks multisig owners
- Location: `contracts/Airdrop/Airdrop.sol` : `startAirdrop`
- Mechanism: The function uses `traitToken.transferFrom(tx.origin, address(this), amount)` to pull tokens. `tx.origin` refers to the original externally owned account (EOA) that initiated the transaction, not the direct caller (`msg.sender`). 
- Impact: If the `owner` of the Airdrop contract is a smart contract wallet (e.g., a Gnosis Safe multisig), `tx.origin` will resolve to the EOA of the multisig signer rather than the multisig contract itself. This will cause the transaction to fail (if the EOA hasn't approved the tokens) or incorrectly pull tokens from the signer's personal wallet instead of the multisig treasury.

## DAOFund: Sandwich attack vulnerability in `receive()`
- Location: `contracts/DAOFund/DAOFund.sol` : `receive`
- Mechanism: The contract automatically swaps incoming ETH for tokens using `uniswapV2Router.swapExactETHForTokens` with `amountOutMin` set to `0`. 
- Impact: Because slippage tolerance is effectively infinite, an attacker or MEV bot can sandwich the transaction. They can buy the token right before the `receive()` trigger, artificially inflating the price, and then sell it immediately after. The DAOFund will be forced to buy tokens at the inflated price, receiving far fewer tokens to burn and resulting in a direct, extractable loss of ETH value from the fund.

## EntityForging / EntityTrading / NukeFund: Division by zero if `taxCut` is 0
- Location: `contracts/EntityForging/EntityForging.sol` : `forgeWithListed`, `contracts/EntityTrading/EntityTrading.sol` : `buyNFT`, `contracts/NukeFund/NukeFund.sol` : `receive`
- Mechanism: The `setTaxCut` functions in these contracts lack a check to prevent the owner from setting `_taxCut` to `0`. The code subsequently performs division operations like `fee / taxCut` and `msg.value / taxCut`.
- Impact: If the owner accidentally or maliciously sets `taxCut` to `0`, it will trigger a division-by-zero panic. This will permanently brick the `forgeWithListed`, `buyNFT`, and `receive` functions, causing a complete Denial of Service (DoS) for trading, forging, and fund deposits.

## EntityForging: Off-by-one error in forging limit checks
- Location: `contracts/EntityForging/EntityForging.sol` : `listForForging` & `forgeWithListed`
- Mechanism: In `listForForging`, the check `forgingCounts[tokenId] <= forgePotential` allows listing when the count exactly equals the potential. In `forgeWithListed`, the merger token's count is incremented *before* the check (`forgingCounts[mergerTokenId]++` followed by `<= mergerForgePotential`). 
- Impact: Due to the off-by-one logic, forger tokens can be used to forge `forgePotential + 1` times, while merger tokens can forge exactly `mergerForgePotential` times. This breaks the intended game mechanics, allowing entities to exceed their maximum forge limits.

## EntropyGenerator: Weak and predictable randomness
- Location: `contracts/EntropyGenerator/EntropyGenerator.sol` : `writeEntropyBatch1`, `writeEntropyBatch2`, `writeEntropyBatch3`, `initializeAlphaIndices`
- Mechanism: Entropy values are generated using `block.number`, `block.timestamp`, and `blockhash(block.number - 1)`. These values are completely deterministic, publicly known before a transaction is mined, and can be manipulated by block validators.
- Impact: Miners, validators, or sophisticated users can predict or manipulate block properties to generate highly favorable entropy values (e.g., maxing out forge potential, performance factor, or nuke factor) for their minted tokens. This ruins the game's economic balance and fairness.

## NukeFund: `minimumDaysHeld` bypass for newly minted tokens
- Location: `contracts/NukeFund/NukeFund.sol` : `canTokenBeNuked` & `contracts/TraitForgeNft/TraitForgeNft.sol` : `_mintInternal`
- Mechanism: `canTokenBeNuked` calculates the holding period using `block.timestamp - nftContract.getTokenLastTransferredTimestamp(tokenId)`. However, `TraitForgeNft` only updates `lastTokenTransferredTimestamp` during secondary transfers (`_beforeTokenTransfer`), leaving it at `0` for newly minted tokens.
- Impact: For a newly minted token, `block.timestamp - 0` results in a massive number (~1.7 billion seconds), which easily exceeds the `minimumDaysHeld` (e.g., 3 days). Attackers can mint tokens and immediately nuke them to drain the NukeFund, completely bypassing the mandatory holding period.

## DevFund: DoS via reverting owner in `receive()`
- Location: `contracts/DevFund/DevFund.sol` : `receive`
- Mechanism: When ETH is received, any indivisible remainder (`remaining > 0`) is sent to the `owner()` via `.call{value: remaining}("")` with a strict `require(success)`. 
- Impact: If the `owner` is a smart contract that reverts on receiving ETH (or becomes one), the `receive()` function will always revert when dust is present. An attacker can purposely send an amount of ETH that is not perfectly divisible by `totalDevWeight` (e.g., 1 wei) to trigger the revert, permanently bricking the DevFund's ability to receive any further deposits.

## TraitForgeNft: Hardcap logic error in `mintWithBudget`
- Location: `contracts/TraitForgeNft/TraitForgeNft.sol` : `mintWithBudget`
- Mechanism: The `while` loop condition checks `_tokenIds < maxTokensPerGen`. However, `_tokenIds` is the global, cumulative token ID counter across all generations, whereas `maxTokensPerGen` is intended to be the limit *per generation*.
- Impact: Once 10,000 total tokens are minted across all generations, `_tokenIds` will equal `maxTokensPerGen`, and the loop will terminate. This incorrectly hardcaps the total supply of the NFT collection to a single generation's limit when using `mintWithBudget`, preventing users from minting in subsequent generations via this function.
