# Audit: 2024-07-traitforge

## NukeFund reentrancy in `receive()` allows fund draining
- Location: `contracts/NukeFund/NukeFund.sol` : `receive()`
- Mechanism: The `receive` function updates the `fund` balance by adding `remainingFund` **before** making an external call to `devAddress`, `owner()`, or `daoAddress`. If the recipient of the dev share is a malicious contract, it can re-enter the `NukeFund` contract by calling `nuke()` inside its fallback. Because `receive` is not protected by `nonReentrant`, the `nuke()` function executes with the already-increased `fund`, allowing the attacker to claim a portion of the newly added funds. This violates the checks-effects-interactions pattern.
- Impact: An attacker can send a large amount of ETH to `NukeFund`, trigger the `receive` function, and in the same transaction call `nuke` on an eligible token to drain a significant portion of the fund (up to 50% of the new balance). The attacker can walk away with more ETH than they sent, stealing from other users’ fund contributions.

## EntropyGenerator predictable entropy allows trait manipulation
- Location: `contracts/EntropyGenerator/EntropyGenerator.sol` : `writeEntropyBatch1/2/3`, `getNextEntropy`
- Mechanism: Entropy values are computed as `keccak256(abi.encodePacked(block.number, i))` and stored in public slots. The batch-writing functions are unprotected and can be called by anyone, allowing an attacker to choose the `block.number` at which slots are initialized. The sequence of entropy values consumed by `getNextEntropy` is deterministic and observable. An attacker can precompute the entropy of upcoming mints and mint only when the resulting traits (forger, forgePotential, nukeFactor) are favourable.
- Impact: Users can mint NFTs with guaranteed desirable properties, completely undermining the randomness that the game economy relies on. This breaks the fairness of the forging and nuking mechanics.

## TraitForgeNft `mintWithBudget` permanently disabled after first generation
- Location: `contracts/TraitForgeNft/TraitForgeNft.sol` : `mintWithBudget()`
- Mechanism: The while-loop condition `_tokenIds < maxTokensPerGen` uses the global token counter `_tokenIds` instead of the per-generation mint count `generationMintCounts[currentGeneration]`. Once the total number of minted tokens reaches `maxTokensPerGen` (10 000), the condition becomes false forever, even though later generations are unlocked and `mintToken` continues to work normally.
- Impact: The `mintWithBudget` function becomes unusable after the first generation is filled, breaking its intended functionality for bulk minting in subsequent generations. Users are forced to use the single-mint `mintToken` even if they want to mint multiple tokens.

## Airdrop accounting fails to track token transfers
- Location: `contracts/TraitForgeNft/TraitForgeNft.sol` : `burn()`, `_mintInternal()`, `_mintNewEntity()`
- Mechanism: The airdrop allocation is tracked via the `initialOwners` mapping, which records the original minter of each token. `addUserAmount` is called for the minter at mint time, and `subUserAmount` is called for the same address when the token is burned. There is no logic to adjust airdrop amounts when a token is transferred. Consequently, burning a token reduces the airdrop allocation of the original minter, not the current owner.
- Impact: A malicious user can acquire tokens from a target, burn them, and decrease the target’s airdrop share. The airdrop distribution becomes disconnected from actual token ownership, leading to unfair and manipulable allocations.

## EntityForging off-by-one allows exceeding forge potential
- Location: `contracts/EntityForging/EntityForging.sol` : `listForForging()`
- Mechanism: The check `forgingCounts[tokenId] <= forgePotential` uses `<=` instead of `<`. After a token has been used as a forger `forgePotential` times, `forgingCounts` equals `forgePotential`. The condition still passes, allowing the token to be listed and forged one extra time beyond its intended limit.
- Impact: Tokens can be used as forgers more times than designed, breaking the scarcity mechanic and giving an unfair advantage to holders of high-forge-potential tokens.

## DAOFund missing slippage protection enables sandwich attacks
- Location: `contracts/DAOFund/DAOFund.sol` : `receive()`
- Mechanism: The `receive` function calls `swapExactETHForTokens` with `amountOutMin = 0` and `deadline = block.timestamp`. This provides no protection against front-running or sandwich attacks. An attacker can manipulate the Uniswap pool before the swap executes, causing the contract to receive a negligible amount of tokens, and then reverse the manipulation after the swap.
- Impact: ETH sent to `DAOFund` with the intention of burning tokens can be stolen by MEV bots. The contract receives almost no tokens, so the burn is ineffective, and the sender’s ETH is lost for no deflationary benefit.

## Airdrop `startAirdrop` uses `tx.origin` causing failure for contract owners
- Location: `contracts/Airdrop/Airdrop.sol` : `startAirdrop()`
- Mechanism: The function calls `traitToken.transferFrom(tx.origin, address(this), amount)`. If the owner is a contract (e.g., a multisig wallet), `tx.origin` will be the EOA that initiated the transaction, not the owner contract. The token transfer will fail because the EOA is unlikely to have approved the Airdrop contract to spend its tokens.
- Impact: The airdrop cannot be started if the owner is a contract, permanently blocking the airdrop functionality. This forces the owner to use an EOA, which may be impractical or insecure.
