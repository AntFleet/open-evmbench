# Audit: 2024-08-phi

## Consensus findings

## Public position-list mutators corrupt curator accounting and can make shares permanently unsellable
*(consensus)*
- Location: `src/Cred.sol` : `_addCredIdPerAddress` / `_removeCredIdPerAddress` (and the sell branch of `_updateCuratorShareBalance`), approx. lines 575–635 — the two helpers immediately after `_updateCuratorShareBalance`.
- Mechanism: Both functions are declared `public` with **no access control**, despite being internal bookkeeping helpers, and they accept an arbitrary `sender_` supplied by the caller. They mutate `_credIdsPerAddress`, `_credIdsPerAddressCredIdIndex`, and `_credIdsPerAddressArrLength` without consistently updating `shareBalance` or `_credIdExistsPerAddress`. An attacker can call `_removeCredIdPerAddress(credId, victim)` to delete a cred from a victim's index array while `_credIdExistsPerAddress[victim][credId] == true` and `shareBalance[credId][victim] > 0` remain untouched, or call `_addCredIdPerAddress` to inject duplicate/garbage entries and desync the length counter and index map.
- Impact: When the victim later sells their *entire* balance of that cred, the sell branch of `_updateCuratorShareBalance` (`currentNum - amount == 0`) re-invokes `_removeCredIdPerAddress`, which now reverts with `WrongCredId`, `IndexOutofBounds`, or `EmptyArray` because the stored index no longer matches. At least one share unit becomes permanently unsellable, and partial sells of other creds can also be bricked by injecting duplicate indices. This is a cheap, unprivileged griefing/DoS that traps a holder's funds in the bonding curve and corrupts protocol state with a single call.

## Buy-refund reentrancy bypasses the share lock (CEI violation in `_handleTrade`)
*(consensus)*
- Location: `src/Cred.sol` : `_handleTrade` (buy branch), approx. lines 510–570 — `cred.currentSupply += amount_;` … `_msgSender().safeTransferETH(excessPayment);` … `lastTradeTimestamp[credId_][curator_] = block.timestamp;`
- Mechanism: The single-trade entry points (`buyShareCred`, `buyShareCredFor`, `sellShareCred`) are **not** `nonReentrant`. On a buy, the share balance and `currentSupply` are increased, then the excess-payment refund (`_msgSender().safeTransferETH(excessPayment)`, a full-gas Solady transfer to the buyer) is executed **before** `lastTradeTimestamp[credId_][curator_]` is written. A contract buyer who deliberately overpays receives the refund callback while it already owns the freshly minted shares but `lastTradeTimestamp` is still stale/zero, so the sell-side check `block.timestamp <= lastTradeTimestamp + SHARE_LOCK_PERIOD` passes.
- Impact: The 10-minute anti-flip lock is defeated and buy/sell become atomic. A flash-funded attacker can flash-borrow ETH → `buyShareCred` a large fraction of a cred → in the refund callback call `CuratorRewardsDistributor.distribute` and then `sellShareCred` to unwind → repay the loan, all in one transaction — capturing curator rewards risk-free whenever the pending pool exceeds trade fees, with no capital lock.

## Claim authorizations are replayable and do not bind quantity (no double-mint guard)
*(consensus)*
- Location: `src/PhiFactory.sol` : `signatureClaim` / `merkleClaim` / `_validateAndUpdateClaimState`, approx. lines 220–300 and 500–525.
- Mechanism: In `signatureClaim` the signed payload is `abi.encode(expiresIn_, minter_, ref_, verifier_, artId_, chainid, data_)` — `mintArgs_.quantity` (and `imageURI`) are taken from unsigned calldata and are never part of the recovered hash. In `merkleClaim` the leaf is `keccak256(keccak256(abi.encode(minter_, leafPart_)))`, committing only `minter_` and `leafPart_`, not the quantity. `_validateAndUpdateClaimState` writes `artMinted[artId_][minter_] = true` and `credMinted[...][minter_] = true` but **never reads them** to reject a repeat claim; the only caps are `maxSupply`, `endTime`, and per-call fee payment. The signature also carries no nonce, so it is replayable for its entire validity window.
- Impact: A single signature, or a single Merkle-eligible leaf, authorizes minting an arbitrary `quantity` and can be replayed repeatedly until `art.maxSupply` is reached or the window/`endTime` passes. The presence of `artMinted`/`credMinted`/`isArtMinted`/`isCredMinted` shows a one-claim-per-art/per-cred restriction was intended; in practice one authorized address can mint an entire drop, denying all other eligible users, while paying only the economically trivial per-mint fee.

---

## Additional findings (single-reviewer)

## Permissionless `distribute` allows just-in-time share buying to siphon accrued curator rewards
*(Reviewer A only)*
- Location: `src/reward/CuratorRewardsDistributor.sol` : `distribute(uint256 credId)`
- Mechanism: `distribute` has no access control and splits the entire accrued `balanceOf[credId]` across the *current* share holders in proportion to their *live* `getShareNumber` reads — there is no snapshot or time-weighting. An attacker can buy a large quantity of shares on the bonding curve immediately before (or, via the `_handleTrade` reentrancy, atomically with) calling `distribute`, capturing a disproportionate fraction of the rewards into their `PhiRewards.balanceOf`, then sell the shares back. A buy→sell round trip recovers principal minus only protocol/creator fees, so net cost is just those fees.
- Impact: Any party can drain a large share of pending curator rewards owed to long-term curators, diluting legitimate holders. Profitable whenever the accrued pool exceeds the round-trip fee cost; combined with the `_handleTrade` reentrancy it requires no capital lock and is flash-loanable. The caller additionally pockets the `withdrawRoyalty` (default 1%) plus rounding dust on every call.

## `buyShareCredFor` can be used to perpetually lock a victim out of selling
*(Reviewer A only)*
- Location: `src/Cred.sol` : `buyShareCredFor` → `_handleTrade` (buy branch sets `lastTradeTimestamp[credId_][curator_] = block.timestamp`)
- Mechanism: `buyShareCredFor` lets anyone buy shares *on behalf of* an arbitrary `curator_`, and each such buy resets `lastTradeTimestamp[credId_][curator_]` to the current time. The sell path enforces `block.timestamp > lastTradeTimestamp + SHARE_LOCK_PERIOD`. An attacker can call `buyShareCredFor(credId, 1, victim, …)` at least once every 10 minutes to continually reset the victim's timestamp.
- Impact: The victim is indefinitely blocked from selling any shares of that cred (liquidity/timing denial of service). The attacker bears the per-share cost (and the victim receives the bought shares), so it is paid griefing rather than profit, but it is fully under attacker control and not preventable by the victim.

## `Cred.setProtocolFeePercent` accepts an unbounded value
*(Reviewer A only)*
- Location: `src/Cred.sol` : `setProtocolFeePercent(uint256 protocolFeePercent_)`
- Mechanism: Unlike `PhiFactory.setProtocolFee` (which enforces `<= 10_000`), this setter has no upper bound. The fee is later used as `price * protocolFeePercent / RATIO_BASE` in `BondingCurve._getProtocolFee`. Setting it `> RATIO_BASE` (100%) makes `protocolFee` exceed `price`, so the sell payout `price - protocolFee - creatorFee` underflows and reverts, and buy cost balloons.
- Impact: A misconfiguration (or compromised/rogue owner) bricks all sells for every cred and inflates buy requirements. Owner-gated, so severity is limited to configuration risk, but the missing bound is a genuine setter-admits-invalid-value defect, underscored by the divergence from the bounded `PhiFactory` setter.

## Unbounded `royaltyBPS` in royalty configuration
*(Reviewer A only)*
- Location: `src/abstract/CreatorRoyaltiesControl.sol` : `_updateRoyalties`
- Mechanism: `_updateRoyalties` only rejects `recipient == address(0) && BPS > 0`; an art creator can set `royaltyBPS` above 10_000, making `royaltyInfo` return a royalty greater than the sale price.
- Impact: EIP-2981 is advisory, so the impact lands on downstream marketplaces that honor the returned value (potentially returning a royalty exceeding the sale price), but the value should be capped.

## Stranded overpayment in claims
*(Reviewer A only)*
- Location: `src/PhiFactory.sol` : `claim` / `batchClaim`
- Mechanism: `claim`/`batchClaim` forward only `mintFee` (resp. `ethValue_[i]`) to the inner claim and never refund `msg.value - mintFee` at the outer level; the inner refund is computed against the already-trimmed value, so it is 0. Any overpayment is left in the factory.
- Impact: Overpaid ETH is stranded in the factory and is sweepable by the owner via `withdraw()`. User-error dependent, low severity.

## Unsigned art config lets callers seize new art
*(Reviewer B only)*
- Location: `src/PhiFactory.sol` : `createArt` / `_createERC1155Data` / `_initializePhiArt`, approx. lines 140–160 and 390–455.
- Mechanism: `createArt` verifies only `signedData`, which decodes to `expiresIn`, `uri`, and `credData`. The caller-controlled `createConfig_` is **not** signed and is used to set `artist`, `receiver`, `maxSupply`, `mintFee`, `startTime`, `endTime`, and `soulBounded`. There is also no requirement that `msg.sender` equals the `artist`.
- Impact: Anyone who obtains or observes a valid art-creation signature can front-run or reuse it with themselves as `artist`/`receiver`, taking update authority and the mint-reward flow for the art. They can also alter supply, fees, timing, and transferability away from what the signer intended.

## Cred creation signature omits creator and royalties
*(Reviewer B only)*
- Location: `src/Cred.sol` : `createCred` / `_createCredInternal`, approx. lines 220–280 and 455–500.
- Mechanism: `createCred` verifies `signedData` for expiry, sender, bonding curve, URL/type fields, and merkle root, but `creator_`, `buyShareRoyalty_`, and `sellShareRoyalty_` are separate unsigned calldata. Those values are stored as the cred creator and royalty rates after only a max-range check.
- Impact: Any authorized sender holding a valid unexpired `createCred` signature can choose an arbitrary `creator` address and set buy/sell royalties up to 50%, assigning metadata control and future creator fees on attacker-chosen terms that the signer never committed to.

