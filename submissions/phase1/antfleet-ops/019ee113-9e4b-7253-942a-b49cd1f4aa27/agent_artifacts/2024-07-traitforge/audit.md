# Audit: 2024-07-traitforge

## Airdrop Token Substitution After Start
- Location: `contracts/Airdrop/Airdrop.sol` : `setTraitToken` / `claim`
- Mechanism: `setTraitToken` has no guard that the airdrop has not started, so the owner can swap `traitToken` to any address after `startAirdrop` has already pulled the legitimate tokens into the contract. When users later invoke `claim`, the contract executes `traitToken.transfer(msg.sender, amount)` against the newly-set token, which the contract does not hold, so the call reverts and all originally deposited tokens are permanently stranded.
- Impact: The owner can grief every claimant out of their airdrop by pointing the contract at a worthless or non‑existent ERC‑20. Alternatively, by setting the token to one they control, transferring that token in, and front‑running claims, they can redirect value flow; in any case legitimate users lose access to the deposited airdrop tokens with no on‑chain recovery.

## Airdrop Uses `tx.origin` for Token Pull
- Location: `contracts/Airdrop/Airdrop.sol` : `startAirdrop`
- Mechanism: `startAirdrop` is `onlyOwner`, but it calls `traitToken.transferFrom(tx.origin, address(this), amount)`. If the owner is a multisig or any contract wallet, `tx.origin` resolves to the externally‑owned account that submitted the underlying transaction rather than the multisig itself, so tokens are pulled from an unrelated EOA. The multisig never needs to (and cannot) approve the Airdrop, breaking the function for the standard secure‑wallet setup and forcing the owner to approve from a hot EOA.
- Impact: The airdrop cannot be safely started from a multisig or smart‑wallet owner. Worse, any contract the owner interacts with that ends up triggering `startAirdrop` will pull tokens from `tx.origin` (the user's EOA) provided that user approved the Airdrop, enabling phishing‑style theft of approved balances.

## NukeFund Pausable DoS via Zero Tax Cut
- Location: `contracts/NukeFund/NukeFund.sol` : `setTaxCut` / `receive`
- Mechanism: `setTaxCut` accepts any `uint256` value without a lower bound. If the owner (or anyone who compromises the owner key) calls `setTaxCut(0)`, every subsequent `receive` call computes `devShare = msg.value / taxCut`, which is a division‑by‑zero and reverts. The same is true for `EntityForging.forgeWithListed`, which computes `devFee = forgingFee / taxCut`.
- Impact: The nuke fund and forging marketplace can be permanently bricked — no ETH can enter the fund and no forge can complete — until governance restores a non‑zero `taxCut`. Because the fund is the sole sink for mint revenue, all minting economics halt.

## Unvalidated Airdrop Reference in NukeFund
- Location: `contracts/NukeFund/NukeFund.sol` : constructor / `setAirdropContract` / `receive`
- Mechanism: The constructor stores `airdropContract = IAirdrop(_airdrop)` with no zero‑address check, and `setAirdropContract` likewise accepts any address. The `receive` function unconditionally calls `airdropContract.airdropStarted()` and `airdropContract.daoFundAllowed()`; passing `address(0)` causes the call to revert, and pointing it at an attacker‑controlled contract lets the attacker steer the dev share between `devAddress`, `owner`, and `daoAddress` at will by toggling those two booleans.
- Impact: Deploying with (or later setting) `address(0)` permanently DoSes `receive`. Pointing it at a malicious implementation lets an attacker redirect the entire dev share of all incoming ETH to an address of their choosing.

## EntityForging Pause Blocks All NFT Transfers
- Location: `contracts/TraitForgeNft/TraitForgeNft.sol` : `_beforeTokenTransfer` calling `EntityForging.cancelListingForForging`
- Mechanism: `TraitForgeNft._beforeTokenTransfer` calls `entityForgingContract.cancelListingForForging(tokenId)` whenever the token is listed. `cancelListingForForging` is gated by `whenNotPaused` and `nonReentrant`. If `EntityForging` is paused (intentionally, by key compromise, or by `setOneYearInDays` / `setMinimumListFee` configuration mistakes), every ERC‑721 transfer, mint, and burn on `TraitForgeNft` reverts inside that hook.
- Impact: Pausing the forging contract freezes the entire NFT collection — no transfers, no mints, no burns, no nuke claims — with no recovery short of unpausing forging. This is a foot‑gun severity denial‑of‑service for the core asset.

## DAOFund Has No Slippage Protection
- Location: `contracts/DAOFund/DAOFund.sol` : `receive`
- Mechanism: `swapExactETHForTokens` is invoked with `amountOutMin = 0`. There is no oracle or minimum‑out check, and the contract performs the swap on every inbound ETH transfer.
- Impact: Any donor that sends ETH to the DAO fund can be sandwich‑attacked: an attacker can front‑run the swap to push the token price down on Uniswap, the DAO receives near‑zero tokens, the attacker back‑runs to restore the price, and the difference is extracted as profit. Because the tokens are immediately burned, the value lost is pure economic waste to the donors and token holders.

## Entropy Is Fully Deterministic and Publicly Readable
- Location: `contracts/EntropyGenerator/EntropyGenerator.sol` : `writeEntropyBatch1/2/3`, `getNextEntropy`, `getPublicEntropy`
- Mechanism: Every entropy value is `uint256(keccak256(abi.encodePacked(block.number, i))) % 10**78` — a pure function of `block.number` and an index. Once any batch is written, the values are permanently visible on chain via the public storage slot reads (and `getPublicEntropy`). `block.number` is chosen by the miner producing the block in which the batch is written, and the batches themselves can be initialized by anyone (`writeEntropyBatch1/2/3` are `public` with no access control).
- Impact: There is no randomness. A miner can choose when to mine the initialization block to seed favorable entropy, and any user can precompute the exact entropy that will be assigned to the next minted/forged token and time their interactions accordingly. Forge potential, forger/merger classification, and nuke factor are all derived from this entropy, so the entire game economy can be gamed for free.

## EntityForging `setOneYearInDays(0)` Allows Unlimited Forging
- Location: `contracts/EntityForging/EntityForging.sol` : `setOneYearInDays` / `_resetForgingCountIfNeeded`
- Mechanism: `_resetForgingCountIfNeeded` resets `forgingCounts[tokenId]` whenever `block.timestamp >= lastForgeResetTimestamp[tokenId] + oneYearInDays`. The setter has no minimum bound; if `oneYearInDays` is set to `0`, the condition is true on every subsequent call, so the forge counter is reset before each new forge.
- Impact: A compromised or malicious owner can trivially bypass the `forgePotential` cap, allowing any listed forger to be merged an unlimited number of times. This collapses the scarcity mechanic of forging and lets the attacker dilute/over‑mint high‑generation entities.

## NukeFund Age Multiplier Overflow DoS
- Location: `contracts/NukeFund/NukeFund.sol` : `setAgeMultplier` / `calculateAge` / `calculateNukeFactor`
- Mechanism: `calculateAge` computes `daysOld * perfomanceFactor * MAX_DENOMINATOR * ageMultiplier / 365` and `calculateNukeFactor` computes `adjustedAge * defaultNukeFactorIncrease / MAX_DENOMINATOR + initialNukeFactor`. There are no bounds on `ageMultiplier`, `defaultNukeFactorIncrease`, or the entropy‑derived inputs; Solidity 0.8 will revert on overflow. Because `canTokenBeNuked` is consulted from `nuke`, and the view functions are also called from off‑chain UIs, an oversized `ageMultiplier` can render the entire nuke flow unsusable.
- Impact: Setting `ageMultiplier` to a large value bricks every `nuke` and every view call that resolves nuke eligibility, denying all holders the ability to burn NFTs for their ETH payout.

## TraitForgeNft `_distributeFunds` Reverts When NukeFund Unset
- Location: `contracts/TraitForgeNft/TraitForgeNft.sol` : `_distributeFunds` / `setNukeFundContract`
- Mechanism: `_distributeFunds` calls `nukeFundAddress.call{value: totalAmount}("")` with no zero‑address check; if `nukeFundAddress` has not been configured (or is set to `address(0)`), the low‑level call returns `success = false` and the `require` reverts. `_mintInternal` and `_mintNewEntity` both invoke this, so any mint path reverts.
- Impact: Until and unless the nuke fund address is configured, the NFT contract cannot mint a single token. The two‑step initialization (deploy NFT, then set fund, then mint) is fragile and allows a misconfigured deployment to brick mints; a future governance change that nullifies `nukeFundAddress` has the same effect.

## Burn Reduces Original Minter's Airdrop Allocation
- Location: `contracts/TraitForgeNft/TraitForgeNft.sol` : `burn` (and `contracts/Airdrop/Airdrop.sol` : `subUserAmount`)
- Mechanism: On burn, `TraitForgeNft` calls `airdropContract.subUserAmount(initialOwners[tokenId], entropy)` regardless of who currently owns the token. Because `initialOwners` is fixed at mint time and `subUserAmount` only checks `!started`, any current holder can grief the original minter's airdrop allocation by burning a transferred token before the airdrop starts.
- Impact: An attacker can purchase or receive a low‑cost NFT from a high‑entropy minter and burn it, slashing the original minter's share of the airdrop. Repeated across many tokens, this can be used to manipulate the `totalValue` denominator and concentrate the airdrop on tokens the attacker retained — effectively a griefing vector that distorts airdrop distribution.
