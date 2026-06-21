# Audit: 2024-08-phi

# Security Audit Report — Phi Protocol (Cred, PhiFactory, PhiNFT1155, Rewards)

Below are **genuine security vulnerabilities** found in the provided code, ordered by severity.

---

## Signature claim replay allows unlimited mints per signature

- **Location:** `PhiFactory.sol` : `signatureClaim` / `_validateAndUpdateClaimState`
- **Mechanism:** `signatureClaim` verifies a backend signature and expiry, then mints, but never records whether a signature (or its digest) was already used. `artMinted[artId][minter]` is set to `true` on every claim but is **never checked** before minting. The same calldata can be resubmitted in separate transactions until `art.numberMinted + quantity > art.maxSupply`.
- **Impact:** Anyone holding one valid signature can mint up to the art’s entire `maxSupply` (not just one NFT), stealing supply from legitimate users and breaking the intended one-claim-per-signature model.

---

## Merkle claim replay allows unlimited mints per proof

- **Location:** `PhiFactory.sol` : `merkleClaim` / `_validateAndUpdateClaimState`
- **Mechanism:** Merkle proof verification is stateless. After a successful claim, nothing invalidates the leaf/proof pair. `credMinted` is written but never read as a gate, and `artMinted` is not enforced. The same `(proof, minter_, leafPart_, artId)` can be replayed repeatedly until `maxSupply` is exhausted.
- **Impact:** A single eligible Merkle leaf can be used to mint many times on the same art, draining `maxSupply` and mint fees/rewards accounting.

---

## Art creation signature replay creates unlimited duplicate arts

- **Location:** `PhiFactory.sol` : `createArt` / `_validateArtCreationSignature`
- **Mechanism:** The signed payload decodes as `(expiresIn, uri, credData)` and does **not** bind `artId`. Each call uses the current `artIdCounter`, and `_validateArtCreation` only prevents reusing the *same* counter value. A single unexpired signature can be replayed to create many distinct arts with identical metadata/configuration.
- **Impact:** One signed approval can spawn unlimited art instances until signature expiry, inflating supply, bypassing intended one-art-per-approval policy, and potentially griefing artists/cred holders.

---

## Cred creation signature replay creates duplicate creds

- **Location:** `Cred.sol` : `createCred`
- **Mechanism:** Like art creation, `createCred` checks signer and expiry but does not track consumed signatures/nonces. Each replay allocates a new `credId` via `credIdCounter++`.
- **Impact:** Attackers can duplicate creds from one signed approval, fragmenting liquidity across fake duplicate markets and breaking cred uniqueness assumptions downstream (NFT linkage, rewards, indexing).

---

## Arbitrary cred creator not bound by signature

- **Location:** `Cred.sol` : `createCred`
- **Mechanism:** Signed data includes `sender` (must equal `msg.sender`) but **not** `creator_`. `creator_` is a separate user-supplied argument passed to `_createCredInternal`. The protocol assigns royalties, attribution, and creator identity to `creator_` without signature binding.
- **Impact:** A caller with a valid self-signed approval can create creds that impersonate any address as creator (e.g., assign royalties to/victim-name a high-profile address), while the caller receives the initial share purchase.

---

## Public cred-index mutators enable sell DoS / position lock

- **Location:** `Cred.sol` : `_addCredIdPerAddress`, `_removeCredIdPerAddress`
- **Mechanism:** These functions are declared **`public`** (not `internal`), with no access control. `_removeCredIdPerAddress(credId, victim)` can be called by anyone when the victim has a tracked position. It removes the cred from the victim’s index arrays/mappings but **does not** change `shareBalance`.
- **Impact:** When the victim later tries to sell their remaining shares to zero, `_updateCuratorShareBalance` calls `_removeCredIdPerAddress` again and reverts (`IndexOutofBounds` / `WrongCredId`). The victim cannot fully exit; value remains locked in the bonding curve for that position (griefing/fund lock).

---

## Single Merkle proof mints across all arts sharing a cred

- **Location:** `PhiFactory.sol` : `merkleClaim` / `_initializePhiArt`
- **Mechanism:** Merkle eligibility is keyed only by `(credChainId, credId)` via `credMerkleRoot[...]`, while mint limits are per `artId`. Creating additional arts for the same cred reuses/overwrites the shared root and does not isolate eligibility per art. A valid proof for `(minter, leafPart)` can be submitted against **any** MERKLE art with that cred.
- **Impact:** Holders of one cred’s allowlist can mint every future art tied to that cred (including arts the artist did not intend to include), and replay amplifies damage across all such arts.

---

## Merkle root overwrite breaks or changes eligibility for existing arts

- **Location:** `PhiFactory.sol` : `_initializePhiArt`
- **Mechanism:** Every art creation writes `credMerkleRoot[credChainId][credId] = merkleRootHash` unconditionally. Later art creation for the same cred overwrites the global root used by all MERKLE claims for that cred.
- **Impact:** Existing arts may suddenly reject previously valid proofs (DoS), or accept proofs from a newly signed root (changing allowlist semantics for already-deployed arts without per-art migration).

---

## Art creation fee can be paid from factory ETH balance (not caller payment)

- **Location:** `PhiNFT1155.sol` : `createArtFromFactory` (called by `PhiFactory.createArt`)
- **Mechanism:** `createArtFromFactory` transfers `artCreateFee` via `protocolFeeDestination.safeTransferETH(artFee)` without requiring `msg.value >= artFee`. Solady’s ETH transfer sends from contract balance. If the caller supplies insufficient `msg.value`, the fee is still taken from the factory/NFT contract’s existing balance.
- **Impact:** Callers can create arts while externalizing creation fees to accumulated contract ETH (prior mint fees/overpayments), stealing pooled funds from the protocol/users.

---

## Soulbound restriction bypass via `transferFrom`

- **Location:** `PhiNFT1155.sol` : (missing override of `transferFrom`)
- **Mechanism:** Soulbound enforcement exists only in overridden `safeTransferFrom` / `safeBatchTransferFrom`. Standard ERC1155 `transferFrom` is not overridden and does not apply the `soulBounded` check.
- **Impact:** “Soulbound” tokens remain transferable through contracts/wallets calling `transferFrom`, defeating the soulbound guarantee.

---

## Missing access control on reward handler enables unauthenticated reward routing

- **Location:** `PhiRewards.sol` : `handleRewardsAndGetValueSent`
- **Mechanism:** This function is `external payable` with no restriction to `PhiNFT1155`/factory. Caller chooses `mintFee_`, `addressesData_`, and reward recipients; only `msg.value == computeMintReward(quantity_, mintFee_)` is checked.
- **Mechanism detail:** In normal flow, mint fee is enforced by factory/NFT path. Here, caller can set `mintFee_ = 0` and still route configured fixed rewards/curator deposits.
- **Impact:** Attackers can invoke reward distribution **without minting an NFT**, underpaying artist/protocol mint fee components while still directing curator deposits and reward balances. This breaks the intended mint→reward coupling and can manipulate curator reward accounting cheaply.

---

## Unbounded protocol fee can brick sells (DoS)

- **Location:** `Cred.sol` : `setProtocolFeePercent`; trade path in `_handleTrade`
- **Mechanism:** `setProtocolFeePercent` has no upper bound (unlike factory’s capped fee setter). On sells, payout is computed as `price - protocolFee - creatorFee`. With sufficiently large fee percentages/royalties, subtraction underflows and reverts in Solidity 0.8.
- **Impact:** Malicious/compromised owner (or misconfiguration) can make sells impossible while buys still work, trapping curator funds in the curve.

---

## Pause bypass is not an issue; reentrancy on single trades is limited

I verified batch paths use `whenNotPaused` internally. Single-trade reentrancy risk is reduced by state updates before external calls, but single trades still lack `nonReentrant` while performing external ETH/reward calls — lower severity than replay issues above.

---

## View/accounting bug (integration risk, not direct theft)

- **Location:** `Cred.sol` : `getPositionsForCurator`
- **Mechanism:** Loop writes to `credIds[i]` / `amounts[i]` but shrinks array length to `index`, causing sparse/wrong entries when some tracked cred IDs are stale.
- **Impact:** Integrators relying on this view can mis-account positions (wrong UX / failed automations). Not a direct on-chain theft path by itself.

---

# Summary table

| Severity | Finding |
|----------|---------|
| Critical | Signature claim replay |
| Critical | Merkle claim replay |
| High | Art creation signature replay |
| High | Cred creation signature replay |
| High | Unbound `creator_` in cred creation |
| High | Public `_removeCredIdPerAddress` sell DoS |
| High | Shared Merkle root across arts |
| High | Merkle root overwrite |
| High | Art creation fee drained from contract balance |
| Medium | Soulbound bypass via `transferFrom` |
| Medium | Unauthenticated `handleRewardsAndGetValueSent` |
| Medium | Unbounded protocol fee sell DoS |

---

# Recommended fixes (guidance only — Ask mode)

1. Add consumed-signature / consumed-leaf / per-art mint bitmaps (`artMinted` must be checked, or use nullifiers).
2. Bind `creator_`, `artId`, and other critical fields inside signed payloads.
3. Change `_addCredIdPerAddress` / `_removeCredIdPerAddress` to `internal`.
4. Use per-art Merkle roots (or include `artId` in leaf), avoid global overwrite.
5. Require `msg.value >= artCreateFee` before fee transfer in `createArtFromFactory`.
6. Override `transferFrom` with the same soulbound guard.
7. Restrict `handleRewardsAndGetValueSent` to factory/NFT caller and validate `mintFee_` against on-chain art config.
8. Cap `protocolFeePercent` (e.g., `<= 10_000`).

If you want, I can switch to Agent mode and produce a patch set or a Slither/foundry test plan for these findings.

