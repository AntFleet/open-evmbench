# Audit: 2024-08-phi

Here is the security audit report for the provided Solidity codebase.

## Public Access to State-modifying Helper Functions
- Location: `Cred.sol` : `_addCredIdPerAddress` & `_removeCredIdPerAddress`
- Mechanism: The internal-acting helper functions `_addCredIdPerAddress` and `_removeCredIdPerAddress` are declared as `public` instead of `internal` or `private`. These functions modify the mapping tracking list mappings (`_credIdsPerAddress`, `_credIdsPerAddressCredIdIndex`, and `_credIdsPerAddressArrLength`) for any user-provided `sender_` address without performing any checks or authorization. 
- Impact: An attacker can directly manipulate any user's credential tracking arrays. They can delete valid configurations for existing positions, resulting in permanent state desynchronization. If the victim later attempts to sell or trade their credentials, the internal execution of `_removeCredIdPerAddress` will encounter invalid indices or key mismatches, permanently bricking transactions and trapping the user's ETH inside the contract.

---

## Out of Bounds Write and Data Loss in Curator Position Queries
- Location: `Cred.sol` : `getPositionsForCurator`
- Mechanism: The function `getPositionsForCurator` allocates `credIds` and `amounts` memory arrays with a length equal to `stopIndex - start_`. Inside the retrieval loop which iterates with index `i` from `start_` to `stopIndex - 1`, it writes values using the instruction `credIds[i] = credId`. Since `i` corresponds to the original offset, any call made with `start_ > 0` will trigger an immediate out-of-bounds array write panic. Additionally, when `start_ == 0` and skipped (non-existent) indices are encountered, it leaves unpopulated indices (defaults of `0`) in the array, after which it resizes the array length to the sequential `index` variable using assembly, truncating the valid entries written at higher offsets.
- Impact: Dapps, systems, and callers will be unable to paginate positions for any curator profile, resulting in transaction reverts or completely corrupted results empty of real positions.

---

## Inevitable Out-of-Gas Denial of Service on Reward Distribution
- Location: `CuratorRewardsDistributor.sol` : `distribute` & `Cred.sol` : `_getCuratorData`
- Mechanism: When a curator sells all of their shares for a credential in `Cred.sol`, their balance in the open Zeppelin EnumerableMap is set to 0. However, the user is never removed from the underlying enumerable keys. As unique addresses trade a given credential over time, the total number of keys in the mapping grows monotonically. When `distribute` is called, it triggers `getCuratorAddresses(credId, 0, 0)`, which forces the contract to loop over the entire historic list of all traders to filter active ones.
- Impact: As trading activity accumulates on popular credentials, calls to `distribute` will inevitably exceed block gas limits and persistently revert, locking all accrued and future curator rewards for that credential inside the contract.

---

## Missing Double-Claim Prevention in Arts Creation
- Location: `PhiFactory.sol` : `_validateAndUpdateClaimState`
- Mechanism: When claiming arts rewards using `signatureClaim` or `merkleClaim`, the validation phase `_validateAndUpdateClaimState` updates state parameters by setting `artMinted[artId_][minter_] = true` and `credMinted[art.credChainId][art.credId][minter_] = true`. However, the helper forgets to verify if `artMinted` or `credMinted` is already true.
- Impact: Whitelisted qualifiers or malicious actors holding a valid signature or Merkle proof can call `claim` and replay their qualifications repeatedly. This permits them to obtain an unlimited volume of NFTs, exhaust scarce collections with low max supplies, and manipulate rewards.

---

## Locked Artist and Creator Excess ETH in Creation Process
- Location: `PhiFactory.sol` : `createArt`
- Mechanism: When an artist calls `createArt` to deploy an ERC1155 NFT, they submit native ETH (`msg.value`) to cover the creation fee. If they submit more than the current `artCreateFee`, the entire payment is routed via raw call to `createArtFromFactory` on the cloned NFT contract. The cloned contract evaluates the precise fee and refunds the remainder (`msg.value - artFee`) back to the factory (`_msgSender()`). Because `PhiFactory.sol` does not contain logic in `createArt` to capture and refund this returned excess value back to the developer/artist, the ETH is permanently trapped in the factory contract.
- Impact: Artists and users will experience direct and irreversible loss of funds if they submit more than the minimum required fee during art initialization.

---

## Uninitialized Parent Upgradeable Contracts inside Clones
- Location: `PhiNFT1155.sol` : `initialize`
- Mechanism: The cloned `PhiNFT1155` contract inherits from OpenZeppelin’s `ERC1155SupplyUpgradeable` and `ERC1155Upgradeable` implementations. However, its initialization sequence fails to invoke `__ERC1155_init()` or `__ERC1155Supply_init()`.
- Impact: Parent internal state structures remain uninitialized, leading to undefined behavior, potential metadata/URI standard compliance failures, or storage corruption in any subsequent system upgrades.
