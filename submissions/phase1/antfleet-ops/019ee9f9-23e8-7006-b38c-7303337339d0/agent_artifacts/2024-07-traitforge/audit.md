# Audit: 2024-07-traitforge

# TraitForge Security Audit Report

Findings below are limited to genuine logic, access-control, accounting, oracle/entropy, and value-loss issues. Centralization by `onlyOwner` is noted only where it creates an exploitable failure mode for users.

---

## Parent NFTs are not burned during forging (unlimited NFT duplication)

- **Location:** `TraitForgeNft.sol` : `forge` / `EntityForging.sol` : `forgeWithListed`
- **Mechanism:** `EntityForging.forgeWithListed` calls `nftContract.forge(...)`, but neither contract burns or transfers `parent1Id` / `parent2Id`. `forge` only mints a new token via `_mintNewEntity`. After forging, the forger and merger NFTs remain in their owners’ wallets.
- **Impact:** An attacker with a forger + merger (across one or two accounts) can repeatedly list the forger, pay the forging fee, and mint new NFTs without destroying parents. This inflates supply, dilutes rarity/rewards, and breaks core game economics. The attack is repeatable until forge-count limits bind the merger (and the forger can be re-listed after each successful forge).

---

## Forger forge-limit off-by-one bypass

- **Location:** `EntityForging.sol` : `listForForging` / `forgeWithListed`
- **Mechanism:** `listForForging` allows listing when `forgingCounts[tokenId] <= forgePotential`. In `forgeWithListed`, the forger’s count is incremented (`forgingCounts[forgerTokenId]++`) with **no** forge-time cap check (unlike the merger, which increments then `require`s). When `forgingCounts == forgePotential` at list time, listing succeeds, then forging pushes the count to `forgePotential + 1`.
- **Impact:** Forgers can perform one extra forge per reset window beyond their intended `forgePotential`, gaining extra minted offspring and fee revenue they should not have.

---

## Predictable / front-runnable entropy (mint rarity manipulation)

- **Location:** `EntropyGenerator.sol` : `writeEntropyBatch1/2/3`, `getNextEntropy`, `getPublicEntropy` / `TraitForgeNft.sol` : `_mintInternal`
- **Mechanism:** Entropy is derived from public on-chain state: batch writes use `keccak256(abi.encodePacked(block.number, i))`, slots are readable via `getPublicEntropy`, and `getNextEntropy` advances deterministically through `(currentSlotIndex, currentNumberIndex)`. Total mint count reveals the next index. A searcher can simulate the next entropy off-chain before submitting `mintToken` / `mintWithBudget`.
- **Impact:** Attackers can cherry-pick mints (only submit when entropy yields favorable forger status, forge potential, nuke factor, etc.) or sandwich honest minters. NFT rarity and downstream fund/forging mechanics become gameable by MEV bots, undermining fairness and economic assumptions.

---

## Unpermissioned entropy initialization with manipulable randomness

- **Location:** `EntropyGenerator.sol` : `writeEntropyBatch1`, `writeEntropyBatch2`, `writeEntropyBatch3`
- **Mechanism:** Batch initialization functions are **public** with no access control. Entropy values depend on `block.number` at call time, so the caller chooses which block’s context is hashed.
- **Impact:** Anyone can initialize batches (or race the owner) at a chosen block to bias `entropySlots`. Combined with public slot reads and deterministic consumption, this amplifies entropy manipulation and lets early minters receive values from attacker-chosen batches.

---

## Minting before entropy initialization yields zero/default entropy

- **Location:** `EntropyGenerator.sol` : `getEntropy` / `TraitForgeNft.sol` : `_mintInternal`
- **Mechanism:** If `writeEntropyBatch*` has not fully populated `entropySlots`, `entropySlots[slotIndex]` is `0`. `getEntropy` still computes a value from that zero slot. Nothing in `TraitForgeNft` requires `getLastInitializedIndex() == maxSlotIndex` before minting.
- **Impact:** Early minters (or anyone minting during partial initialization) receive predictable, low-quality entropy, breaking role/rarity assignment. Attackers monitoring initialization state can mint in that window to secure advantaged or known traits.

---

## Generation increment DoS (`initializeAlphaIndices` access mismatch)

- **Location:** `TraitForgeNft.sol` : `_incrementGeneration` / `EntropyGenerator.sol` : `initializeAlphaIndices`
- **Mechanism:** `_incrementGeneration` calls `entropyGenerator.initializeAlphaIndices()`, but that function is `onlyOwner` on `EntropyGenerator`. Unless `TraitForgeNft` is the owner of `EntropyGenerator`, the call reverts when a generation hits `maxTokensPerGen`.
- **Impact:** After the first generation fills, further mints that trigger `_incrementGeneration` revert. The protocol can become permanently stuck at generation 1 (or current gen), blocking normal operation.

---

## `tx.origin` used as token payer in airdrop funding

- **Location:** `Airdrop.sol` : `startAirdrop`
- **Mechanism:** `traitToken.transferFrom(tx.origin, address(this), amount)` pulls tokens from `tx.origin`, not `msg.sender`. `startAirdrop` is `onlyOwner`, but the token source is the EOA at the root of the call chain.
- **Impact:** If the owner is a contract (multisig, timelock, governance), tokens are pulled from the initiating EOA, not the owner contract—likely causing failed starts or unintended funding from the wrong wallet. In phishing scenarios, a malicious intermediary contract can trick an approved EOA into a transaction that drains their TRAIT balance when the owner starts the airdrop.

---

## DAOFund swaps with zero minimum output (sandwich / MEV)

- **Location:** `DAOFund.sol` : `receive`
- **Mechanism:** `swapExactETHForTokens` is called with `amountOutMin = 0` and `deadline = block.timestamp`, giving no slippage protection.
- **Impact:** MEV searchers can sandwich ETH sent to `DAOFund`, manipulating the pool so the contract receives far fewer tokens than fair value for the ETH. Value intended for buy-and-burn is captured by attackers; users/donors lose expected economic effect.

---

## Excess ETH not refunded on forge

- **Location:** `EntityForging.sol` : `forgeWithListed`
- **Mechanism:** The function checks `msg.value >= forgingFee` but only distributes `forgingFee`. Any `msg.value - forgingFee` remains in the `EntityForging` contract with no refund path.
- **Impact:** Users who overpay (accidentally or via UI rounding) permanently lose excess ETH locked in the contract.

---

## Secondary owner can grief initial minter’s airdrop weight by burning

- **Location:** `TraitForgeNft.sol` : `burn` / `Airdrop.sol` : `subUserAmount`
- **Mechanism:** Airdrop weight is tracked on `initialOwners[tokenId]`, not the current holder. Before the airdrop starts, `burn` calls `airdropContract.subUserAmount(initialOwners[tokenId], entropy)` while only requiring `isApprovedOrOwner(msg.sender, tokenId)`.
- **Impact:** A secondary market buyer (or anyone approved) can burn an NFT to subtract entropy from the **original minter’s** airdrop allocation without gaining that allocation themselves. This enables griefing/competitive sabotage of whitelist participants’ shares.

---

## `mintWithBudget` uses global token ID cap instead of per-generation cap

- **Location:** `TraitForgeNft.sol` : `mintWithBudget`
- **Mechanism:** The loop condition is `budgetLeft >= mintPrice && _tokenIds < maxTokensPerGen`. `_tokenIds` is total supply across all generations, while `maxTokensPerGen` is per-generation (10,000). After 10,000 total NFTs exist, the loop never runs even if the current generation has capacity.
- **Impact:** `mintWithBudget` becomes unusable after global supply reaches `maxTokensPerGen`, while `mintToken` still works. This is a broken access path to minting (availability/logic bug) that can block users relying on budget minting in later generations.

---

## Division by zero if `taxCut` is set to zero

- **Location:** `EntityForging.sol` : `forgeWithListed` / `EntityTrading.sol` : `buyNFT` / `NukeFund.sol` : `receive`
- **Mechanism:** Each contract computes `value / taxCut` with no `require(taxCut > 0)`. `setTaxCut` allows the owner to set `taxCut = 0`.
- **Impact:** Forging, NFT purchases, and NukeFund ETH receipt all revert on division by zero, causing protocol-wide DoS of fee-bearing flows. While owner-triggered, a misconfiguration or compromised owner key bricks core functionality.

---

## Airdrop / ERC20 transfer success not checked

- **Location:** `Airdrop.sol` : `startAirdrop`, `claim`
- **Mechanism:** `transferFrom` and `transfer` return values are ignored (no `SafeERC20`). On tokens that return `false` instead of reverting on failure, the call can fail silently.
- **Mechanism detail on `claim`:** State is updated after transfer (`userInfo[msg.sender] = 0` follows `transfer`), so a silent failed transfer still zeroes eligibility.
- **Impact:** With a non-standard ERC20, users can lose airdrop entitlement without receiving tokens; or `startAirdrop` can mark the airdrop started while fewer/no tokens were actually received, causing later claims to fail and mis-accounting `totalTokenAmount`.

---

## `nukeFactorMaxParam` / `maxAllowedClaimDivisor` zero can brick `nuke`

- **Location:** `NukeFund.sol` : `nuke`
- **Mechanism:** `maxAllowedClaimAmount = fund / maxAllowedClaimDivisor` has no guard against `maxAllowedClaimDivisor == 0`. Owner can set it via `setMaxAllowedClaimDivisor(0)`.
- **Impact:** All `nuke` calls revert (division by zero), permanently disabling the primary fund withdrawal mechanism.

---

## Forge-fee routing fails if `nukeFundAddress` unset

- **Location:** `EntityForging.sol` : `forgeWithListed` / `EntityTrading.sol` : `buyNFT` / `TraitForgeNft.sol` : `_distributeFunds`
- **Mechanism:** `EntityForging` sends `devFee` to `nukeFundAddress` without a zero-address check (`EntityTrading` and mint paths have similar dependency). Default `nukeFundAddress` is unset until `setNukeFundAddress`.
- **Impact:** Forging and trading (and mint fund distribution) revert on ETH transfer failure, creating DoS until admin configuration. Not attacker-profitable, but a real operational vulnerability in deployment ordering.

---

## Inconsistent forge-potential derivation (logic error across contracts)

- **Location:** `EntityForging.sol` : `listForForging`, `forgeWithListed` / `EntropyGenerator.sol` : `deriveTokenParameters`
- **Mechanism:** `EntityForging` uses `uint8((entropy / 10) % 10)` as forge potential, while `EntropyGenerator.deriveTokenParameters` uses `getFirstDigit(entropy)` (most significant digit). The comment in forging says “5th digit” but the math does not match `deriveTokenParameters` or documented intent.
- **Impact:** Forging limits and role logic diverge from the entropy system’s stated parameter derivation. Entities may be allowed more or fewer forges than designed, enabling unintended repeated forging relative to protocol spec (compounds the parent-non-burn issue for mergers/forgers).

---

## Summary severity table

| Severity | Finding |
|----------|---------|
| **Critical** | Parent NFTs not burned on forge (unlimited duplication) |
| **High** | Predictable/front-runnable entropy |
| **High** | Public manipulable entropy batch init |
| **High** | Minting on uninitialized entropy |
| **High** | Generation increment DoS (`initializeAlphaIndices`) |
| **High** | DAOFund zero slippage (sandwich) |
| **Medium** | Forger forge-limit off-by-one |
| **Medium** | `tx.origin` in `startAirdrop` |
| **Medium** | Burn griefing of airdrop allocations |
| **Medium** | Excess ETH locked in `forgeWithListed` |
| **Medium** | `mintWithBudget` wrong cap check |
| **Low/Medium** | Unchecked ERC20 return values in Airdrop |
| **Low** | `taxCut` / `maxAllowedClaimDivisor` zero DoS (owner misconfig) |

---

**Note:** `DevFund.sol` follows a standard MasterChef-style accrual pattern with `nonReentrant` on `claim` and partial-payment handling in `safeRewardTransfer`; no clear external exploit path was identified there beyond owner trust assumptions.

If you want, I can switch to Agent mode and propose concrete patches for the critical/high items (parent burns, entropy access control, CEI/SafeERC20, slippage params, etc.).

