# Audit: 2024-07-traitforge

# Security Audit Report

## Excess ETH not refunded in forgeWithListed
- Location: `EntityForging.sol` : `forgeWithListed`
- Mechanism: The function requires `msg.value >= forgingFee` but never refunds the difference when `msg.value > forgingFee`. The contract has no withdraw/recovery function, so any excess ETH sent is permanently locked in the contract.
- Impact: Users who send more ETH than the forging fee lose the excess permanently. An attacker could also front-run a legitimate `forgeWithListed` call with a higher `msg.value` to cause the victim's transaction to overpay (though the victim would see the required fee and could send exact change).

## Forger forge-potential bypass (off-by-one)
- Location: `EntityForging.sol` : `listForForging` / `forgeWithListed`
- Mechanism: `listForForging` checks `forgingCounts[tokenId] <= forgePotential` (allows listing when count equals potential). Then `forgeWithListed` increments `forgingCounts[forgerTokenId]++` **without** re-checking against `forgePotential`. If a forger has already forged exactly `forgePotential` times, it can still list (since `count == potential` passes `<=`) and then forge once more, exceeding its intended limit.
- Impact: A forger token can forge one additional time beyond its declared `forgePotential`, minting extra forged entities and earning extra forging fees that should not have been allowed.

## mintWithBudget uses global token counter instead of per-generation count
- Location: `TraitForgeNft.sol` : `mintWithBudget`
- Mechanism: The `while` loop condition is `budgetLeft >= mintPrice && _tokenIds < maxTokensPerGen`. `_tokenIds` is a global counter across **all** generations, while `maxTokensPerGen` (10 000) is per-generation. Once 10 000 total tokens have been minted (filling generation 1), the condition `_tokenIds < maxTokensPerGen` is permanently false, so `mintWithBudget` can never mint into generation 2 or later—even though `_mintInternal` correctly handles generation increments.
- Impact: Bulk minting via `mintWithBudget` is completely broken for all generations after the first, denying a core protocol function to users.

## DAOFund receive() burns all tokens held by the contract
- Location: `DAOFund.sol` : `receive`
- Mechanism: After swapping incoming ETH for the Trait token via Uniswap, the contract calls `token.burn(token.balanceOf(address(this)))`. This burns **every** Trait token the contract holds, not just the ones purchased in this call. If any tokens were previously sent to the contract (intentionally or by mistake), they are irreversibly burned.
- Impact: Any pre-existing Trait token balance in the DAOFund contract is destroyed whenever someone triggers the receive function. An attacker can send a small amount of Trait tokens to the contract and then trigger a buy-back, burning not only the purchased tokens but also the attacker's tokens and any other tokens held by the contract.

## Airdrop.startAirdrop uses tx.origin for transferFrom
- Location: `Airdrop.sol` : `startAirdrop`
- Mechanism: `traitToken.transferFrom(tx.origin, address(this), amount)` uses `tx.origin` instead of `msg.sender`. If the owner calls `startAirdrop` through an intermediary contract (e.g., a multisig, Gnosis Safe, or proxy), `tx.origin` will be the underlying EOA, not the calling contract. The `transferFrom` approval must come from `tx.origin`, which may not match the entity that approved the tokens.
- Impact: The function may fail when called through a contract wallet (the approval from the wallet won't satisfy `transferFrom` from `tx.origin`). More critically, if the owner is tricked into calling a malicious intermediary that calls `startAirdrop`, the `tx.origin`-based `transferFrom` pulls tokens from the EOA regardless of the calling contract's intent.

## NukeFund nukeFactor never increases with age (ageMultiplier defaults to zero)
- Location: `NukeFund.sol` : `calculateAge` / `calculateNukeFactor`
- Mechanism: `calculateAge` computes `age = (daysOld * performanceFactor * MAX_DENOMINATOR * ageMultiplier) / 365`. The state variable `ageMultiplier` is never set in the constructor and defaults to `0`. With `ageMultiplier == 0`, `age` is always `0`, so `calculateNukeFactor` returns only the static `initialNukeFactor` (based on entropy) regardless of how long a token has been held.
- Impact: The nuke factor never increases over time, contradicting the intended design where older tokens become more valuable to nuke. Unless the owner manually calls `setAgeMultplier`, the entire age-based nuke mechanic is non-functional.

## _beforeTokenTransfer makes external call to potentially unset entityForgingContract
- Location: `TraitForgeNft.sol` : `_beforeTokenTransfer`
- Mechanism: `_beforeTokenTransfer` unconditionally calls `entityForgingContract.getListedTokenIds(firstTokenId)`. If `entityForgingContract` has not been set (still `address(0)`) or has been set to an invalid address, this external call reverts, blocking **every** token transfer—including minting (`_mint` triggers `_beforeTokenTransfer`). There is no zero-address check or try/catch guard.
- Impact: If the owner forgets to call `setEntityForgingContract` before minting begins, or sets it to a broken/malicious contract, all minting and transfers are permanently blocked. A malicious `entityForgingContract` could also arbitrarily revert to DoS the entire NFT contract.
