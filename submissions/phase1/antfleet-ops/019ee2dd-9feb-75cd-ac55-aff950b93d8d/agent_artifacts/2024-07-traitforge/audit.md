# Audit: 2024-07-traitforge

 ## Airdrop funding pulls tokens from `tx.origin`
- Location: `contracts/Airdrop/Airdrop.sol` : `startAirdrop`
- Mechanism: `startAirdrop` uses `traitToken.transferFrom(tx.origin, address(this), amount)` instead of `transferFrom(msg.sender, ...)`. In any call path where the owner is a contract (multisig, governance, etc.), `tx.origin` is the externally-owned account that initiated the outer transaction, while `msg.sender` is the owner contract. The contract therefore withdraws tokens from the transaction originator rather than from the authorized caller.
- Impact: A compromised or malicious intermediate contract can cause the airdrop contract to drain Trait tokens from an EOA's wallet, or the owner contract can be tricked into starting an airdrop funded by a different account.

## Airdrop deposit amount is not reconciled with `totalValue`
- Location: `contracts/Airdrop/Airdrop.sol` : `startAirdrop`
- Mechanism: `startAirdrop` records `totalTokenAmount = amount` but never validates `amount` against the sum of all user allocations (`totalValue`). The claim formula `(totalTokenAmount * userInfo[user]) / totalValue` assumes the deposited tokens match the recorded weights.
- Impact: If `amount < totalValue`, every claimant receives proportionally fewer tokens than their recorded allocation and the airdrop is underfunded. If `amount > totalValue`, tokens are left unused in the contract, breaking the intended 1:1 mapping between allocation weights and deposited tokens.

## `mintWithBudget` caps total supply at generation-1 size
- Location: `contracts/TraitForgeNft/TraitForgeNft.sol` : `mintWithBudget`
- Mechanism: The minting loop checks `while (budgetLeft >= mintPrice && _tokenIds < maxTokensPerGen)`. `_tokenIds` is the global token-id counter, while `maxTokensPerGen` is the per-generation cap (10,000). Once `_tokenIds` reaches 10,000, the loop exits even though generations 2–10 are intended to be mintable.
- Impact: `mintWithBudget` can never mint tokens beyond generation 1, even though `_mintInternal` will later increment generations. Users must fall back to `mintToken` to reach later generations, and the bulk-minting function is effectively bricked for the majority of the collection.

## Minting does not enforce `maxGeneration`
- Location: `contracts/TraitForgeNft/TraitForgeNft.sol` : `_mintInternal`, `_incrementGeneration`
- Mechanism: `_incrementGeneration` increments `currentGeneration` without checking `maxGeneration`. `_mintInternal` only checks the per-generation cap, not the global generation limit.
- Impact: `mintToken` (and `mintWithBudget` if its loop condition is fixed) can mint tokens in generation 11, 12, etc., inflating supply beyond the advertised 10-generation maximum. The `maxGeneration` limit is only enforced in `forge`.

## Excess ETH is not refunded in `forgeWithListed`
- Location: `contracts/EntityForging/EntityForging.sol` : `forgeWithListed`
- Mechanism: The function requires `msg.value >= forgingFee` but only distributes `forgingFee` (dev fee + forger share). Any ETH sent above `forgingFee` remains in the `EntityForging` contract, and there is no withdrawal function.
- Impact: Users who overpay are permanently locked out of their excess ETH. The contract accumulates unrecoverable funds.

## `taxCut` can be set to zero causing division by zero
- Location: `contracts/EntityForging/EntityForging.sol` : `setTaxCut` / `forgeWithListed`; `contracts/EntityTrading/EntityTrading.sol` : `setTaxCut` / `buyNFT`; `contracts/NukeFund/NukeFund.sol` : `setTaxCut` / `receive`
- Mechanism: All three contracts let the owner set `taxCut` to any value, including `0`, and then divide by it (`forgingFee / taxCut`, `msg.value / taxCut`, etc.) without validation.
- Impact: An owner can accidentally or maliciously set `taxCut = 0`, which reverts all subsequent forges, NFT sales, or ETH deposits into `NukeFund`, causing a denial of service of core protocol operations.

## `oneYearInDays` can be set to zero allowing infinite forging
- Location: `contracts/EntityForging/EntityForging.sol` : `setOneYearInDays` / `_resetForgingCountIfNeeded`
- Mechanism: The owner can set `oneYearInDays` to `0`. In `_resetForgingCountIfNeeded`, the condition `block.timestamp >= lastForgeResetTimestamp[tokenId] + oneYear` then becomes always true, so `forgingCounts[tokenId]` is reset to `0` on every call.
- Impact: Forgers and mergers can bypass the intended forge-potential limit indefinitely within a single block, flooding the protocol with forged NFTs and breaking the scarcity model.

## Fund-sink addresses lack zero-address validation
- Location: `contracts/TraitForgeNft/TraitForgeNft.sol` : `setNukeFundContract`; `contracts/EntityForging/EntityForging.sol` : `setNukeFundAddress`; `contracts/EntityTrading/EntityTrading.sol` : `setNukeFundAddress`; `contracts/NukeFund/NukeFund.sol` : `setDevAddress`, `setDaoAddress`
- Mechanism: None of these setters validate that the new address is non-zero. The contracts then forward ETH to these addresses via low-level calls.
- Impact: If an owner accidentally sets a sink to `address(0)`, mint fees, forging taxes, trading taxes, or dev/DAO shares are permanently burned instead of being distributed.

## `DAOFund` swaps with zero slippage protection
- Location: `contracts/DAOFund/DAOFund.sol` : `receive`
- Mechanism: The `receive` function calls `uniswapV2Router.swapExactETHForTokens` with `amountOutMin = 0` and `deadline = block.timestamp`, providing no protection against price movement.
- Impact: MEV bots and adversarial validators can sandwich incoming ETH, delivering far fewer tokens than expected. The contract then burns those tokens, resulting in a much lower (or effectively zero) token burn for the same ETH input.

## Entropy is generated from predictable on-chain data
- Location: `contracts/EntropyGenerator/EntropyGenerator.sol` : `writeEntropyBatch1`, `writeEntropyBatch2`, `writeEntropyBatch3`, `initializeAlphaIndices`
- Mechanism: Entropy slots and the special `999999` selection point are derived from `block.number`, `blockhash(block.number - 1)`, and `block.timestamp`. These values are known before the transaction is mined and can be influenced by validators/block builders.
- Impact: Users can compute upcoming entropy values off-chain and time mints to obtain high-value traits (e.g., high nuke factor, forger status). Validators can manipulate the seed to grant themselves favorable entropy, undermining the randomness of the collection.

## Entropy padding corrupts token parameters
- Location: `contracts/EntropyGenerator/EntropyGenerator.sol` : `getEntropy`
- Mechanism: After slicing a 6-digit entropy value, the contract right-pads it with zeros: `paddedEntropy = entropy * (10 ** (6 - numberOfDigits(entropy)))`. This transforms values like `123` into `123000` instead of left-padding to preserve the original numeric properties.
- Impact: Token parameters derived from entropy are corrupted. In particular, `performanceFactor = entropy % 10` becomes `0` for any entropy that required padding (roughly 90% of tokens), and `forgePotential = (entropy / 10) % 10` is shifted, breaking the intended distribution of game attributes.

## `NukeFund.receive` can be frozen by `taxCut = 0`
- Location: `contracts/NukeFund/NukeFund.sol` : `receive` / `setTaxCut`
- Mechanism: As noted for the other `taxCut` setters, `NukeFund.setTaxCut` accepts `0`. The `receive` function immediately executes `uint256 devShare = msg.value / taxCut`, which reverts on division by zero.
- Impact: All ETH inflows to the nuke fund (mint fees, forging taxes, trading taxes) are permanently blocked, freezing the fund and disabling the `nuke` payout mechanism.
