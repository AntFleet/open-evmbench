# Audit: 2024-07-traitforge

Here is the smart-contract security audit of the provided codebase.

## Off-by-one forging limit verification allows extra forgings
- Location: `EntityForging.sol` : `listForForging`
- Mechanism: In `listForForging`, the contract checks the `forgingCounts` of the token before it is incremented during `forgeWithListed`. Crucially, it uses a minor-or-equal check: `require(forgePotential > 0 && forgingCounts[tokenId] <= forgePotential)`. If the maximum limit of forging is `forgePotential`, a user whose token has already reached that maximum limit (i.e., `forgingCounts[tokenId] == forgePotential`) will still pass this require statement and be allowed to list their token for forging again. Once listed, the forge can occur, pushing `forgingCounts` up to `forgePotential + 1`.
- Impact: Forgers are able to forge one extra time beyond their designated `forgePotential` limit, bypassing synthetically-enforced scarcity mechanics and inflating the supply of minted descendant NFTs.

## Permanent architectural deadlock between `Airdrop` and `TraitForgeNft`
- Location: `Airdrop.sol` : `setTraitToken` / `addUserAmount` / `subUserAmount`
- Mechanism: During minting and burning in `TraitForgeNft.sol`, the contract calls `airdropContract.addUserAmount(...)` and `airdropContract.subUserAmount(...)`. These functions in `Airdrop.sol` are guarded by the `onlyOwner` modifier. Consequently, the `Airdrop` contract must have its owner set to the `TraitForgeNft` contract for standard minting and burning to function. However, critical setup functions in `Airdrop.sol` (such as `setTraitToken` and `allowDaoFund`) also use the `onlyOwner` modifier, yet `TraitForgeNft` has no external wrapper functions to forward calls to them.
- Impact: If the owner of `Airdrop` is set to the admin, standard mints/burns will revert, bricking key protocol functions. If the owner of `Airdrop` is set to `TraitForgeNft`, admin functions can never be called, leaving `traitToken` as `address(0)` and making it impossible for users to claim their airdropped tokens.

## Predictable sequential entropy allows users to easily snipe rare NFTs
- Location: `EntropyGenerator.sol` : `getNextEntropy` / `getPublicEntropy`
- Mechanism: The generated pseudo-random values are loaded into the storage array `entropySlots` sequentially. The `getNextEntropy` function simply reads these values strictly sequentially from index `0` to `769` using a public index pointer. Because all slots and indices are fully public (readable via `getPublicEntropy` or directly from blockchain storage), any user can know the exact entropy value of the next NFT to be minted before submitting a transaction.
- Impact: Sophisticated users can monitor the upcoming slot and index sequence and selectively execute mints only when a rare or high-value entity (such as a high-potential "Forger" or the designated `999999` "Golden Ticket") is next in line. Normal users will be left with degraded and low-value entities.

## Inoperable `mintWithBudget` in Generation 2 and beyond
- Location: `TraitForgeNft.sol` : `mintWithBudget`
- Mechanism: In `mintWithBudget`, the while-loop condition relies on: `while (budgetLeft >= mintPrice && _tokenIds < maxTokensPerGen)`. The variable `_tokenIds` tracks the absolute global count of all tokens minted across all generations. However, `maxTokensPerGen` is a static constant representing the limit *per generation* (set to `10,000`). Once the contract successfully transitions to generation 2, `_tokenIds` will inevitably be greater than `maxTokensPerGen`, causing the loop condition to evaluate as false.
- Impact: As soon as generation 2 begins, `mintWithBudget` becomes entirely bricked. It will immediately complete without minting any tokens and refunding all sent ETH.

## MEV frontrunning and sandwich attacks on `DAOFund` swaps
- Location: `DAOFund.sol` : `receive()`
- Mechanism: When the `DAOFund` contract receives ETH, it automatically swaps the incoming funds through UniswapV2 for the project's native `Trait` tokens before immediately burning them. However, inside the `swapExactETHForTokens` call, the `amountOutMin` parameter is hardcoded to `0`:
  ```solidity
  uniswapV2Router.swapExactETHForTokens{ value: msg.value }(0, path, address(this), block.timestamp);
  ```
- Impact: Highly active MEV bots can easily sandwich other users sending ETH to the `DAOFund` (or large automated developer distributions). The bot can manipulate pool prices before and after the transaction, causing the fund to get nearly zero tokens for their ETH, effectively siphoning and stealing the value during swaps.

## Use of `tx.origin` in `Airdrop.startAirdrop` blocks Multisig and Smart Contract owners
- Location: `Airdrop.sol` : `startAirdrop`
- Mechanism: The function `startAirdrop` pulls funds from the contract owner by executing:
  ```solidity
  traitToken.transferFrom(tx.origin, address(this), amount);
  ```
  If the owner of the `Airdrop` contract is a multisig wallet (e.g. Gnosis Safe) or an administrative smart contract, the `msg.sender` of standard calls is the multisig, but the `tx.origin` is the EOA of the user signing/executing the transaction. The contract will attempt to pull the tokens from the signer's individual wallet instead of the multisig itself.
- Impact: The protocol cannot use secure multisig/smart contract ownership configurations. Any attempt by a multisig to start the airdrop will fail because
