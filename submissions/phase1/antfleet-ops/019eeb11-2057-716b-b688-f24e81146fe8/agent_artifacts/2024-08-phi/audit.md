# Audit: 2024-08-phi
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

# Phi Protocol — Merged Security Audit (6 reports: opus-4-8 ×3, gpt-5.5 ×3)

*Distinct findings identified across inputs: 17. Findings in this output: 17. No findings dropped.*

## Consensus findings

## Public position-bookkeeping mutators are `public` (no access control)
*(consensus, 6 of 6 reports)*
- Location: `src/Cred.sol` : `_addCredIdPerAddress` / `_removeCredIdPerAddress`
- Mechanism: Both helpers mutate `_credIdsPerAddress`, `_credIdsPerAddressCredIdIndex`, and `_credIdsPerAddressArrLength` for an arbitrary `sender_`, are declared `public` with no caller check, and never touch the parallel `shareBalance` / `_credIdExistsPerAddress` state that `_updateCuratorShareBalance` keeps in sync. `_removeCredIdPerAddress(credId, victim)` pops the victim's array entry while `_credIdExistsPerAddress` stays `true` and `shareBalance` is unchanged; `_addCredIdPerAddress` pushes duplicates and overwrites the index mapping.
- Impact: Anyone can desync any holder's position arrays for free. When the victim later sells their entire position, `_updateCuratorShareBalance`'s `(currentNum - amount) == 0` branch re-invokes `_removeCredIdPerAddress`, which now reverts with `EmptyArray` / `WrongCredId` / `IndexOutofBounds`, permanently bricking the full-balance exit (last share unsellable, shares non-transferable) and corrupting `getPositionsForCurator` / `getCuratorAddresses`. Renewable after any re-buy.

## Claim authorization is replayable — `artMinted`/`credMinted` set but never checked, no nonce
*(consensus, 5 of 6 reports)*
- Location: `src/PhiFactory.sol` : `signatureClaim` / `merkleClaim` / `_validateAndUpdateClaimState`
- Mechanism: `_validateAndUpdateClaimState` writes `artMinted[artId][minter]` and `credMinted[...]` but never reads them before minting, and signature claims carry no nonce or consumed-claim marker. The only gate is `numberMinted + quantity <= maxSupply`.
- Impact: An eligible minter (or anyone holding their signature/proof) can replay the same authorization repeatedly until `maxSupply` is exhausted, draining supply from other eligible users and overwriting the minter's per-token URI/data; each replay only costs the mint fee.
- Reviewer disagreement: opus shot 1 surfaced the same replay but declined to classify it as a vulnerability, arguing every replay is fully paid by the caller and yields no protocol-level value extraction.

## `buyShareCredFor` / `batchBuyShareCred` let a third party reset a victim's sell lock
*(consensus, 5 of 6 reports)*
- Location: `src/Cred.sol` : `buyShareCredFor` / `batchBuyShareCred` → `_handleTrade` / `_executeBatchTrade`
- Mechanism: These accept an arbitrary `curator_`, and the buy branch unconditionally writes `lastTradeTimestamp[credId_][curator_] = block.timestamp`. The sell guard blocks the curator's entire balance while `block.timestamp <= lastTradeTimestamp + SHARE_LOCK_PERIOD`, with no consent check from `curator_`.
- Impact: An attacker can buy 1 share "for" a victim every <10 minutes to keep the victim's lock perpetually fresh, indefinitely preventing them from selling any position in that cred (denial of exit) and forcing unsolicited shares onto them. Economically bounded (attacker pays each rising buy, up to `MAX_SUPPLY` 999), but a real targeted DoS.

## Art-creation signature does not bind config / caller / nonce — front-run and replay
*(consensus, 4 of 6 reports)*
- Location: `src/PhiFactory.sol` : `createArt` / `_validateArtCreationSignature` / `_createERC1155Data`
- Mechanism: The signed payload covers only `(expiresIn, uri, credData)`. It does not bind the caller, a nonce, or the attacker-controlled `CreateConfig` (`artist`, `receiver`, `maxSupply`, `mintFee`, `startTime`, `endTime`, `soulBounded`); `createArt` uses the current `artIdCounter`.
- Impact: Anyone who obtains or observes a valid unexpired creation signature can front-run or replay it to create art with themselves as artist/receiver and arbitrary supply/fees/timing, gaining art-admin rights (`updateArtSettings`) and redirecting artist rewards; replay also spawns duplicate art entries each charging `artCreateFee`.

## Reentrancy in `_handleTrade` buy refund bypasses `SHARE_LOCK_PERIOD`
*(consensus, 4 of 6 reports)*
- Location: `src/Cred.sol` : `_handleTrade` (buy branch `_msgSender().safeTransferETH(excessPayment)` executed before the `lastTradeTimestamp` write; no `nonReentrant`, unlike `_executeBatchTrade`)
- Mechanism: On a buy, shares and `currentSupply` are credited, then excess ETH is refunded to `_msgSender()` before `lastTradeTimestamp[credId_][curator_]` is set; the single-trade path has no reentrancy guard. From the refund callback the attacker holds freshly minted shares with a stale `lastTradeTimestamp` (0 for a fresh address), so the sell-lock check passes and an immediate `sellShareCred` in the same tx succeeds.
- Impact: A contract buyer can atomically buy and sell shares meant to be locked for 10 minutes. The opus reports extend this: reenter `CuratorRewardsDistributor.distribute(credId)` while holding a momentary mega-position to capture the bulk of the accrued reward pool, then unwind — a flash-buy→distribute→sell that nets the reward pool minus round-trip fees whenever the pot exceeds those fees.
- Reviewer disagreement: opus shot 2 examined this exact path and defended it, stating it could not construct a profitable exploit because state is updated before the external calls and the bonding curve is symmetric, so CEI is "effectively preserved." *(conflicting reviews: 1 of 6 reports defended this code path)*

## Claim authorization does not bind mint quantity
*(consensus, 3 of 6 reports)*
- Location: `src/PhiFactory.sol` : `signatureClaim` / `merkleClaim` / `_validateAndUpdateClaimState`
- Mechanism: `mintArgs_.quantity` is outside the signed `encodeData_` and outside the Merkle leaf (`minter_` + `leafPart_`); `_validateAndUpdateClaimState` only checks `numberMinted + quantity <= maxSupply`.
- Impact: A user with one valid signature or proof can choose any quantity up to the remaining art supply, minting far more than intended and exhausting supply for other eligible users, as long as the corresponding fees are paid.

## `Cred.setProtocolFeePercent` has no upper bound
*(consensus, 3 of 6 reports)*
- Location: `src/Cred.sol` : `setProtocolFeePercent` (and `initialize`); consumed in `_handleTrade` / `_validateAndCalculateBatch` via `BondingCurve._getProtocolFee`
- Mechanism: Stores `protocolFeePercent` with no cap (unlike `PhiFactory.setProtocolFee`, which reverts above `10_000`). If `protocolFee + creatorFee > price`, the sell path's `price - protocolFee - creatorFee` underflows under checked arithmetic.
- Impact: A misconfigured or compromised owner can set the fee above ~100% and make every `sellShareCred` / `batchSellShareCred` revert across all creds, permanently trapping holders' ETH in the bonding-curve reserve, while buys require 2–3× the curve price.

## Late buyers capture accrued curator rewards (no holder snapshot at deposit)
*(consensus, 3 of 6 reports)*
- Location: `src/reward/CuratorRewardsDistributor.sol` : `deposit` / `distribute`
- Mechanism: Rewards accumulate per `credId` in `balanceOf[credId]`, but `distribute` splits the whole accumulated balance by *current* `getShareNumber`; nothing snapshots who held shares while the reward accrued. `SHARE_LOCK_PERIOD` constrains only selling, not buying or reward eligibility.
- Impact: An attacker who observes a large `balanceOf[credId]` can buy a dominant position just before distribution, call permissionless `distribute` to capture a pro-rata slice of historical rewards (plus the caller royalty cut), then sell after the 10-minute lock — diluting holders who owned shares during accrual. Not atomic (must tolerate the lock); profitability depends on pot size vs. fees/slippage.

## Uninitialized proxies can be front-run during deployment
*(consensus, 2 of 6 reports)*
- Location: `script/Deploy.s.sol` : `run` (and `script/DeployWoCred.s.sol` : `run`)
- Mechanism: The `Cred` and `PhiFactory` ERC1967 proxies are deployed with empty initializer calldata and `initialize()` is called in a separate transaction, leaving a gap where the proxy is externally initializable. (PhiNFT1155 clones are initialized atomically inside `createArt`, so they are not exposed.)
- Impact: An attacker watching the mempool can front-run `initialize` to set themselves as owner/signer/fee recipient and gain upgrade control over `PhiFactory` and/or `Cred`.

## Minority findings

## `createCred` royalty recipient and rates are caller-controlled, not signed
*(minority, 1 of 6 reports)*
- Location: `src/Cred.sol` : `createCred` (params `creator_`, `buyShareRoyalty_`, `sellShareRoyalty_`; also `updateCred`)
- Mechanism: Signer authorization covers only `signedData_` (`expiresIn, sender, <unused>, bondingCurve, credURL, credType, verificationType, merkleRoot`). `creator_` (the perpetual `CREATOR_ROYALTY_FEE` recipient) and `buyShareRoyalty_` / `sellShareRoyalty_` (bounded only by `MAX_ROYALTY_RANGE = 5000` = 50%) are passed unsigned and never validated against the signed payload.
- Impact: A caller holding any valid create-cred signature can assign the perpetual royalty stream to an arbitrary address and set buy/sell royalties up to 50% regardless of signer intent; via `updateCred` a creator can raise sell royalties to 50% after others have bought (sellers only partly protected by `minPrice`).

## Signed authorizations replayable across deployments/chains (no domain separation)
*(minority, 1 of 6 reports)*
- Location: `src/Cred.sol` : `createCred` / `updateCred` / `_recoverSigner`; `src/PhiFactory.sol` : `signatureClaim` / `_validateArtCreationSignature`
- Mechanism: Signatures are recovered over `ECDSA.toEthSignedMessageHash(keccak256(signedData_))` with no domain separator, nonce consumption, or `address(this)` binding; decoded chain-id-like fields are discarded instead of being compared to `block.chainid`.
- Impact: A valid unexpired signature from the same signer can be replayed on another contract or chain, or reused until expiry to duplicate creations/claims or restore stale updates.

## Historical zero-balance holders can permanently DoS curator reward distribution
*(minority, 1 of 6 reports)*
- Location: `src/Cred.sol` : `_updateCuratorShareBalance` / `_getCuratorData`; `src/reward/CuratorRewardsDistributor.sol` : `distribute`
- Mechanism: Selling a final share does `shareBalance[credId_].set(sender_, 0)` but leaves the address inside the `EnumerableMap`; `distribute` calls `getCuratorAddresses(credId, 0, 0)`, iterating the entire historical map.
- Impact: An attacker can cycle many addresses through buy/sell-to-zero to bloat the holder map until `distribute` exceeds the block gas limit, permanently stranding that cred's rewards.

## `CreatorRoyaltiesControl._updateRoyalties` accepts royalty BPS above 100%
*(minority, 1 of 6 reports)*
- Location: `src/abstract/CreatorRoyaltiesControl.sol` : `_updateRoyalties` (`royaltyBPS` field is `uint32`); reached via `PhiNFT1155.updateRoyalties` / `PhiFactory.updateArtSettings`
- Mechanism: The only validation is `royaltyRecipient == address(0) && royaltyBPS > 0`; there is no `royaltyBPS <= ROYALTY_BPS_TO_PERCENT (10_000)` bound, so a creator can set BPS up to `type(uint32).max` and `royaltyInfo` returns `royaltyAmount = royaltyBPS * salePrice / 10_000`, which can exceed `salePrice`.
- Impact: ERC-2981 marketplaces reading `royaltyInfo` receive a royalty larger than the sale price, causing secondary-sale settlement to revert or overpay. Unlike Cred share royalties (capped at `MAX_ROYALTY_RANGE`), this token-royalty path has no ceiling.

## `BondingCurve._getCreatorFee` falls through on `supply_ == 0` (missing `return`)
*(minority, 1 of 6 reports)*
- Location: `src/curve/BondingCurve.sol` : `_getCreatorFee`
- Mechanism: For `supply_ == 0` it sets `creatorFee = 0` but does not return; execution continues and overwrites it with `(price_ * royaltyRate) / RATIO_BASE`. The trade path (`getPriceData`) correctly returns `creatorFee = 0` at `supply_ == 0`, so the after-fee view functions disagree with what is actually charged.
- Impact: View-only divergence — `getBuyPriceAfterFee` / `getSellPriceAfterFee` / batch price views over- or under-quote at `supply_ == 0`, feeding wrong values to integrators/front-ends or any contract that trusts these quotes for accounting.

## `Cred.getPositionsForCurator` writes results at the wrong index
*(minority, 1 of 6 reports)*
- Location: `src/Cred.sol` : `getPositionsForCurator`
- Mechanism: Result arrays are sized `stopIndex - start_`, but the loop assigns to `credIds[i]` / `amounts[i]` using the source index `i` (running from `start_`) rather than the compacted counter; for `start_ > 0` this is out of bounds, and skipped entries (`_credIdExistsPerAddress` false) land in wrong slots, with a truncating `mstore(..., index)` returning garbage.
- Impact: View-only — the paginated getter reverts for `start_ > 0` and returns incorrect data otherwise, corrupting any consumer that reads curator positions through this interface.

## `PhiFactory.claim` / `batchClaim` pay the mint fee from the contract's balance, not the caller's
*(minority, 1 of 6 reports)*
- Location: `src/PhiFactory.sol` : `claim` (`this.merkleClaim{value: mintFee}` / `this.signatureClaim{value: mintFee}`) and `batchClaim`
- Mechanism: `claim` computes `mintFee = getArtMintFee(...)` and forwards exactly that via a self-call, but never checks `msg.value` against `mintFee`; the forwarded value is drawn from the factory's own ETH balance, and the downstream `_validateAndUpdateClaimState` guard sees the forwarded `mintFee` and always passes. The factory routinely holds residual ETH (overpayment kept by `claim`; `PhiNFT1155.createArtFromFactory` refunds `msg.value - artFee` back to the factory itself).
- Impact: Any caller can invoke `claim` / `batchClaim` with `msg.value` far below the real fee; the shortfall is silently financed from the factory's residual balance. An attacker who is the art `receiver`/`ref` can route those factory-funded rewards into their own withdrawable `PhiRewards.balanceOf` and `withdraw`, minting for free and converting protocol residual into stolen funds (precondition: factory holds ≥ `mintFee` of residual ETH).

## Permissionless `distribute` skims the distributor royalty/dust to any caller
*(minority, 1 of 6 reports)*
- Location: `src/reward/CuratorRewardsDistributor.sol` : `distribute`
- Mechanism: `distribute` is callable by anyone and sends `royaltyfee` (owner-configurable up to `MAX_ROYALTY_RANGE`) plus rounding dust to `_msgSender()`, taken from `balanceOf[credId]` before the remaining rewards are deposited for curators.
- Impact: Any external account, with no relationship to the cred or reward deposit, can call or front-run distribution for any cred and capture the distributor royalty cut from curator rewards.
- Reviewer disagreement: opus shots 1 and 3 examined `distribute` and defended it — opus3 states the rounding dust is "correctly swept to the caller" and opus1 that `distribute` "conserves value," treating the caller payout as intended. *(conflicting reviews: 2 of 6 reports defended this code path)*

