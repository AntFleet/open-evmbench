# Audit: 2023-10-nextgen

## Reentrancy in minting paths bypasses per-address caps
- **Location:** `smart-contracts/MinterContract.sol` : `mint` (also reachable through `burnToMint` and `burnOrSwapExternalToMint`)
- **Mechanism:** The minter calls `gencore.mint`, `gencore.burnToMint`, or `gencore.mint` inside `burnOrSwapExternalToMint`, all of which execute `_safeMint` in `NextGenCore`. `_safeMint` calls `onERC721Received` on the recipient before `NextGenCore` increments `tokensMintedPerAddress` / `tokensMintedAllowlistAddress` and before the minter finishes its own accounting. Because the counters are still at their old values during the callback, a contract recipient can reenter `NextGenMinterContract.mint` and pass the `maxAllowance` check again.
- **Impact:** An attacker can mint far more tokens than the per-address cap allows, up to the collection’s total supply, breaking allowlist and public-sale limits.

## Reentrancy in external burn-or-swap mint via safeTransferFrom
- **Location:** `smart-contracts/MinterContract.sol` : `burnOrSwapExternalToMint`
- **Mechanism:** Before any state update or minting, the function calls `IERC721(_erc721Collection).safeTransferFrom(ownerOfToken, burnOrSwapAddress[externalCol], _tokenId)`. If the configured `burnOrSwapAddress` is a contract, its `onERC721Received` hook executes while the minter is mid-transaction and before the external NFT is considered consumed. With no reentrancy guard, that contract can reenter `burnOrSwapExternalToMint` (it now owns the token and can approve the minter) and mint repeatedly from the same external NFT.
- **Impact:** A callback-capable burn-or-swap address can be used to mint an arbitrary number of tokens from the target collection, inflating supply and draining minting fees.

## No refund of excess minting payments
- **Location:** `smart-contracts/MinterContract.sol` : `mint`, `burnToMint`, `burnOrSwapExternalToMint`
- **Mechanism:** Each payable mint function checks `msg.value >= requiredPrice` but never returns the surplus. The full `msg.value` is added to `collectionTotalAmount`, and there is no user-facing withdrawal path for overpayments.
- **Impact:** Users who send more than the exact price permanently lose the excess ETH; it can only be recovered by an admin through `emergencyWithdraw` or `payArtist`.

## Predictable on-chain randomness
- **Location:** `smart-contracts/RandomizerNXT.sol` : `calculateTokenHash`; `smart-contracts/XRandoms.sol` : `randomNumber`, `randomWord`
- **Mechanism:** `NextGenRandomizerNXT` derives token hashes from `blockhash(block.number - 1)`, `block.prevrandao`, `block.timestamp`, and values from `XRandoms`. All of these sources are public and/or miner/validator-influenceable at the time the mint transaction is included; there is no VRF, commit-reveal, or other secure randomness source.
- **Impact:** Block builders or sophisticated attackers can predict or bias token hashes, allowing them to mint tokens with desirable traits or avoid unfavorable outcomes.

## Expired delegations still authorize minting
- **Location:** `smart-contracts/DelegationManagementContract.sol` : `retrieveGlobalStatusOfDelegation`, `retrieveTokenStatus`; `smart-contracts/MinterContract.sol` : `mint`, `burnOrSwapExternalToMint`
- **Mechanism:** `DelegationManagementContract` records an `expiryDate`, but `retrieveGlobalStatusOfDelegation` and `retrieveTokenStatus` return `true` whenever any delegation record exists, regardless of expiry. `NextGenMinterContract` uses these functions to authorize mints and never checks the expiry itself.
- **Impact:** A delegated wallet can keep minting on behalf of a delegator long after the delegation was supposed to expire, bypassing the intended time-bound access control.

## Sub-delegation checks ignore expiry and locks
- **Location:** `smart-contracts/DelegationManagementContract.sol` : `registerDelegationAddressUsingSubDelegation`, `revokeDelegationAddressUsingSubdelegation`
- **Mechanism:** Both functions verify sub-delegation rights by calling `retrieveDelegators` for `USE_CASE_SUB_DELEGATION`, which returns active and inactive records without checking `expiryDate`. They also do not verify the sub-delegator’s `globalLock`, `collectionLock`, or `collectionUsecaseLock` status.
- **Impact:** An address whose sub-delegation has expired or been locked can still register or revoke delegations for the original delegator, retaining unauthorized control.

## Malicious highest bidder can block auction settlement
- **Location:** `smart-contracts/AuctionDemo.sol` : `claimAuction`
- **Mechanism:** `claimAuction` unconditionally calls `IERC721(gencore).safeTransferFrom(ownerOfToken, highestBidder, _tokenid)`. If the highest bidder is a smart contract that does not implement `IERC721Receiver` or returns a non-magic value, `safeTransferFrom` reverts the entire transaction.
- **Impact:** A malicious highest bidder can deploy a contract that rejects ERC721 tokens, permanently preventing the auction from being settled and locking the NFT and all bidder funds in the auction contract.

## No-active-bid revert blocks admin auction claim
- **Location:** `smart-contracts/AuctionDemo.sol` : `returnHighestBidder` (used in `WinnerOrAdminRequired`)
- **Mechanism:** `returnHighestBidder` reverts with `"No Active Bidder"` when there is no active bid. The `WinnerOrAdminRequired` modifier evaluates `returnHighestBidder` before the admin checks, so the `require` argument itself reverts even if `msg.sender` is a global or function admin.
- **Impact:** If all bids are cancelled or no bids were ever placed, admins cannot call `claimAuction` to close the auction, leaving the token stuck.

## Failed ETH transfers in claimAuction are ignored
- **Location:** `smart-contracts/AuctionDemo.sol` : `claimAuction`
- **Mechanism:** The function captures the `success` boolean from the low-level ETH transfers to `owner()` and losing bidders but never requires `success` to be true. It also sets `auctionClaim[_tokenid] = true` before the transfers, so the transaction continues even if a recipient reverts.
- **Impact:** If the owner or a losing bidder is a reverting contract, the auction is marked as claimed and the NFT is transferred, but the corresponding ETH remains trapped in the contract with no withdrawal function.

## payArtist ignores failed transfers and allows zero addresses
- **Location:** `smart-contracts/MinterContract.sol` : `payArtist`; `smart-contracts/MinterContract.sol` : `proposePrimaryAddressesAndPercentages` / `proposeSecondaryAddressesAndPercentages`
- **Mechanism:** `payArtist` zeros `collectionTotalAmount[_collectionID]` before sending ETH to primary/team addresses and does not revert when a transfer fails. Additionally, the propose functions do not validate that the proposed payment addresses are non-zero, so a non-zero percentage can be assigned to `address(0)`.
- **Impact:** A reverting recipient or a zero address causes royalty/team payments to fail silently; the collection balance is zeroed and the funds are either stuck in the minter or sent to `address(0)` and lost.

## Core/randomizer update functions lack contract validation
- **Location:** `smart-contracts/MinterContract.sol` : `updateCoreContract`; `smart-contracts/RandomizerNXT.sol` : `updateCoreContract`, `updateRandomsContract`; `smart-contracts/RandomizerRNG.sol` : `updateCoreContract`; `smart-contracts/RandomizerVRF.sol` : `updateCoreContract`
- **Mechanism:** These admin functions accept an arbitrary address and do not verify that the new target implements the expected interface (unlike `updateAdminContract`, which checks `isAdminContract`). A compromised function admin or a configuration mistake can point the minter or randomizer at any contract.
- **Impact:** An attacker-controlled core or randomizer address can be used to mint tokens, set token hashes, or drain RNG balances/subscriptions.

## On-chain tokenURI injection via user-supplied tokenData
- **Location:** `smart-contracts/NextGenCore.sol` : `tokenURI` / `retrieveGenerativeScript`; `smart-contracts/MinterContract.sol` : `mint` (allowlist `_tokenData`)
- **Mechanism:** During allowlist minting, the caller supplies `_tokenData`, which is stored verbatim. When a collection admin later enables `onchainMetadata`, `tokenURI` and `retrieveGenerativeScript` concatenate this user-controlled string directly into a JSON data URI and into JavaScript source without escaping or validation.
- **Impact:** A malicious minter can inject arbitrary JSON, HTML, or script content into the token’s metadata and generative artwork, misleading marketplaces and frontends or executing XSS in applications that render the on-chain `tokenURI`.
