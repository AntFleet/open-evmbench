# Audit: 2024-07-traitforge

Here are the security vulnerabilities found in the codebase:

## `TraitForgeNft` minting reverts due to incorrect access control in `Airdrop`
- Location: `Airdrop.sol` : `addUserAmount()` and `TraitForgeNft.sol` : `_mintInternal()`
- Mechanism: In `TraitForgeNft`, whenever an entity is minted, it attempts to call `airdropContract.addUserAmount()` to credit the user's entropy balance for the airdrop. However, `addUserAmount` (and `subUserAmount`) inside `Airdrop.sol` are protected by the `onlyOwner` modifier. The `Owner` role is a single address; if it's held by an EOA to initialize the airdrop (`setTraitToken`, `startAirdrop`), then `TraitForgeNft` will not be authorized and all mint calls will revert. Conversely, if `TraitForgeNft` is made the owner, there's no way to invoke the setup functions since `TraitForgeNft` lacks passthrough functions to configure the airdrop.
- Impact: Core functionality is completely paralyzed. Users will be unable to mint or forge any NFTs because the transaction will forcibly revert upon interacting with the `Airdrop` contract. 

## `mintWithBudget` becomes completely unusable after Generation 1
- Location: `TraitForgeNft.sol` : `mintWithBudget()`
- Mechanism: The method contains a loop condition `while (budgetLeft >= mintPrice && _tokenIds < maxTokensPerGen)`. The variable `_tokenIds` is an ever-increasing global counter of all tokens minted across the entire contract, whereas `maxTokensPerGen` is meant to be the limit for a *single* generation (10,000). Once the first generation is completely minted out, `_tokenIds` will be `10,000`. At this point, the loop condition `_tokenIds < maxTokensPerGen` will permanently evaluate to `false`. 
- Impact: Users will be unable to use the `mintWithBudget` batch-minting functionality for Generation 2 through 10, severely degrading user experience and increasing gas costs for bulk mints. 

## Forgers can exceed their maximum breed allowance (forgePotential) natively
- Location: `EntityForging.sol` : `listForForging()` and `forgeWithListed()`
- Mechanism: `listForForging` correctly requires that the `forgingCounts` is strictly less than or equal to `forgePotential` (`forgingCounts[tokenId] <= forgePotential`). However, in `forgeWithListed`, the protocol implements `forgingCounts[forgerTokenId]++` without validating that the count is still under the `forgePotential` cap, explicitly assuming it was pre-validated in `listForForging`. If a user lists their forger precisely when `forgingCounts == forgePotential` (which correctly passes the check in `listForForging`), `forgeWithListed` will increment the count anyway, bringing `forgingCounts` to `forgePotential + 1`.  
- Impact: Malicious users can consistently override the strict mathematical breeding limit defined by the token's entropy, artificially inflating the supply of entities bred from high-quality forgers. 

## Incorrect zero-padding in `EntropyGenerator` alters entity stats wildly
- Location: `EntropyGenerator.sol` : `getEntropy()`
- Mechanism: When slicing 6 digits out of a large random number slot, `getEntropy` extracts a raw integer value and attempts to pad it with leading zeroes. However, the logic implemented pushes the digits leftward like so: `entropy * (10 ** (6 - numberOfDigits(entropy)))`. If an extracted segment was `000123`, the integer evaluated is just `123`. The custom `numberOfDigits` function sees `123` as having 3 digits, so it multiplies `123` by `10 ** 3`. The final result becomes `123000`. 
- Impact: By moving zeroes from the left of the padding to the right of the integer, the values generated are artificially modified by orders of magnitude. Because gameplay parameters are derived from specific digits (e.g. `nukeFactor`, `forgePotential`), an identity intended to correspond to `123` is completely rewritten to `123000`, drastically unbalancing random property assignments.
