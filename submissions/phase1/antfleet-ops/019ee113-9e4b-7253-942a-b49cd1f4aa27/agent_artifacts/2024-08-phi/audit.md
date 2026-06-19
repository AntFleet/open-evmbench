# Audit: 2024-08-phi

# Security Audit Findings

## 1. Public State-Mutating Helper Functions Lack Access Control
- **Location:** `src/Cred.sol` : `_addCredIdPerAddress`, `_removeCredIdPerAddress`
- **Mechanism:** Both functions are declared `public` with no access-control modifier, making them callable by any external account. An attacker can invoke `_addCredIdPerAddress(credId_, victim)` to push arbitrary `credId` values into a victim's `_credIdsPerAddress` array and overwrite `_credIdsPerAddressCredIdIndex`. Likewise, `_removeCredIdPerAddress` can be called with arbitrary parameters to corrupt the swap-and-pop logic. Because the array length counter `_credIdsPerAddressArrLength` is incremented on every external call, the invariant between `userCredIds.length`, `_credIdsPerAddressArrLength`, and the index map is broken.
- **Impact:** An attacker can corrupt any user's per-curator credId index, leading to incorrect or out-of-bounds results in `getPositionsForCurator`, forced reverts when victims try to remove legitimate credIds, and griefing where victims appear to hold creds they never bought (or don't appear to hold creds they do).

## 2. Out-of-Bounds Memory Write in `getPositionsForCurator`
- **Location:** `src/Cred.sol` : `getPositionsForCurator`
- **Mechanism:** The function allocates result arrays of length `stopIndex - start_` (valid indices 0 to `stopIndex - start_ - 1`), but the population loop writes to `credIds[i]` and `amounts[i]` where `i` iterates from `start_` to `stopIndex - 1`. When `start_ > 0`, the writes target indices `start_` … `stopIndex - 1`, which are past the end of the allocated memory. The subsequent `assembly { mstore(credIds, index) }` resizes to `index`, which can be smaller than `start_`, leaving the OOB writes permanently corrupting adjacent memory.
- **Impact:** Any caller invoking `getPositionsForCurator` with `start_ > 0` triggers an out-of-bounds memory write. This can corrupt the free-memory pointer or other memory structures, causing subsequent allocations to overwrite critical data, or forcing the transaction to revert in unpredictable ways.

## 3. Missing Reentrancy Guard on Claim Functions
- **Location:** `src/PhiFactory.sol` : `claim`, `signatureClaim`, `merkleClaim`, `batchClaim`
- **Mechanism:** The `nonReentrant` modifier is only applied to `createArt`. The public/external claim functions update state (`artMinted`, `credMinted`, `art.numberMinted`) in `_validateAndUpdateClaimState` and then perform an external low-level call to the art contract (`art.artAddress.call{...}`) which in turn calls into `PhiRewards` and optionally `CuratorRewardsDistributor`. There is no reentrancy guard preventing a malicious or compromised art contract (or any contract in the value-transfer chain) from re-entering `merkleClaim` / `signatureClaim` / `claim` before state writes complete.
- **Impact:** A malicious or hijacked art contract implementation could re-enter claim functions to bypass the per-cred one-mint check (`credMinted` is only checked per cred, not per art) and inflate `art.numberMinted`, effectively minting beyond the intended supply or stealing ETH that should fund later payouts.

## 4. No Per-Art Duplicate-Mint Prevention
- **Location:** `src/PhiFactory.sol` : `_validateAndUpdateClaimState`
- **Mechanism:** The function sets `artMinted[artId_][minter_] = true` unconditionally and increments `art.numberMinted` by `quantity_` on every call, but never checks whether `artMinted[artId_][minter_]` is already true. Only the cred-level `credMinted` flag acts as a single-mint gate. A single user holding multiple valid signatures or merkle proofs (or re-entering as described above) can call `signatureClaim` / `merkleClaim` repeatedly for the same `artId_` and mint additional tokens up to `maxSupply`.
- **Impact:** A user with multiple valid authorizations (or via reentrancy) can drain an art's `maxSupply` to themselves, preventing other legitimate minters from claiming and breaking the art's economics.

## 5. Creator Fee Mis-calculated in Bonding-Curve View Functions
- **Location:** `src/curve/BondingCurve.sol` : `_getCreatorFee`
- **Mechanism:** The function sets `creatorFee = 0` when `supply_ == 0` but does not `return`, so execution falls through to the unconditional `creatorFee = (price_ * royaltyRate) / RATIO_BASE;` line that overwrites the zero. This makes the view functions `getBuyPriceAfterFee` and `getSellPriceAfterFee` (which call `_getCreatorFee`) report a non-zero creator fee even when supply is zero, while the actual trade path (`getPriceData`) correctly returns zero creator fee at supply zero via an early return.
- **Impact:** Off-chain consumers using `getCredBuyPriceWithFee` / `getCredSellPriceWithFee` (and the batch equivalents) receive inflated price quotes on the first mint/supply-zero state, leading to mis-priced transactions, failed UX, or users overpaying relative to on-chain execution.

## 6. Excess ETH Not Refunded in `PhiFactory.claim` / `batchClaim`
- **Location:** `src/PhiFactory.sol` : `claim`, `batchClaim`
- **Mechanism:** `claim` forwards exactly `mintFee` to `this.merkleClaim` / `this.signatureClaim`; any additional ETH sent with the original call remains stuck in the factory. In `batchClaim`, each call forwards `ethValue_[i]` and the contract validates `msg.value == totalEthValue`, but if `ethValue_[i] > mintFee` the excess is refunded to the factory (not the original user) inside `_processClaim`. The factory has no logic to forward such refunds back to the original `msg.sender`.
- **Impact:** Users who miscalculate or send safety-margin ETH lose the difference. The contract balance grows with stranded user funds that only the owner can extract via `withdraw()`.

## 7. `forge-std/console2` Imported in Production Contracts
- **Location:** `src/curve/BondingCurve.sol`, `src/reward/CuratorRewardsDistributor.sol`
- **Mechanism:** Both contracts import `forge-std/console2.sol`, a development-only debugging library. Deploying with this import increases bytecode size, may pull in unintended behavior, and signals that untested debug paths could exist.
- **Impact:** Not a direct exploit vector, but indicates production code hygiene issues and potential for unintended side effects (e.g., log emission costs, dependency surface).

## 8. `protocolFeePercent` and `mintProtocolFee` Have No Effective Upper Bound Beyond Owner Trust
- **Location:** `src/Cred.sol` : `setProtocolFeePercent`; `src/PhiFactory.sol` : `setProtocolFee`
- **Mechanism:** `setProtocolFeePercent` in `Cred` has zero validation, allowing the owner to set `protocolFeePercent` to any value (including > `RATIO_BASE = 10_000`), which would make `protocolFee` exceed the entire trade price, effectively allowing the protocol to seize 100%+ of trade value. `setProtocolFee` in `PhiFactory` does cap at 10_000, but `Cred` does not.
- **Impact:** A compromised or malicious owner of `Cred` can set `protocolFeePercent` to an arbitrarily large value, causing every buy to transfer nearly all user ETH to `protocolFeeDestination` and breaking the economic model.

## 9. `PhiFactory.createArt` Lacks Zero-Address Validation for `artist` / `receiver`
- **Location:** `src/PhiFactory.sol` : `createArt`, `_createERC1155Data`
- **Mechanism:** Neither `createArt` nor `_validateArtCreation` checks that `createConfig_.artist` or `createConfig_.receiver` are non-zero. An art can be created with `receiver = address(0)`, which causes all claims to revert in `PhiRewards.depositRewards` (`if (receiver_ == address(0) …) revert InvalidAddressZero()`), permanently bricking the art. Similarly, an art with `artist = address(0)` can never be updated because `onlyArtCreator` will always fail.
- **Impact:** An attacker (or careless operator) can create arts that are permanently unclaimable or unmanageable, wasting gas and the deterministic CREATE2 address slot for that cred.

## 10. `PhiNFT1155` Imports `ReentrancyGuardUpgradeable` but Never Uses It
- **Location:** `src/art/PhiNFT1155.sol` : contract inheritance + `__ReentrancyGuard_init`
- **Mechanism:** `ReentrancyGuardUpgradeable` is inherited and initialized, but no function is marked `nonReentrant`. The storage slot is reserved and `__ReentrancyGuard_init` is called, but the guard is never enforced. Given that `claimFromFactory` makes an external call to `IPhiRewards.handleRewardsAndGetValueSent` (which itself calls `curatorRewardsDistributor.deposit` when `chainSync_` is true), a reentrancy vector exists.
- **Impact:** A malicious `curatorRewardsDistributor` (or future changes to `PhiRewards`) could re-enter `claimFromFactory` to mint additional NFTs to the same minter within a single transaction, bypassing the supply and one-per-cred checks in `PhiFactory`.

---

**Summary:** The most critical issues are the unprotected public array-mutation helpers and the OOB memory write in `Cred` (findings 1 and 2), both of which can be triggered by any external caller. Findings 3, 4, and 10 represent reentrancy and missing-validation vectors in the claim flow. Findings 5–9 are logic errors and centralization risks.
