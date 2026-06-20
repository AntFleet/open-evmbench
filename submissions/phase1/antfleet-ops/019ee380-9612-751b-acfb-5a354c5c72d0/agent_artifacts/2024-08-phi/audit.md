# Audit: 2024-08-phi

Below are the genuine security vulnerabilities I found in this codebase.

## Position-tracking mutators are `public` (arbitrary state corruption)
- Location: `src/Cred.sol` : `_addCredIdPerAddress` / `_removeCredIdPerAddress`
- Mechanism: Both internal-helper functions that maintain the `_credIdsPerAddress`, `_credIdsPerAddressArrLength`, and `_credIdsPerAddressCredIdIndex` bookkeeping are declared `public` instead of `internal`. They contain no access control and no caller restriction, so any external account can call them directly with an arbitrary `sender_`/`credId_`. An attacker can push bogus credIds into any user's array, desynchronize the index mappings, or pop entries, breaking the invariant that the legitimate `_updateCuratorShareBalance` path relies on.
- Impact: An attacker can corrupt any curator's position list. By forcing the array/index mappings out of sync, the next legitimate `sellShareCred`/balance update that triggers `_removeCredIdPerAddress` will revert with `WrongCredId`/`IndexOutofBounds`/`EmptyArray`, permanently bricking that user's ability to sell out of a position. It also poisons all `getPositionsForCurator` reads.

## Anyone can indefinitely lock a victim's shares via `buyShareCredFor`
- Location: `src/Cred.sol` : `buyShareCredFor` → `_handleTrade` (buy branch)
- Mechanism: On every buy, `_handleTrade` sets `lastTradeTimestamp[credId_][curator_] = block.timestamp`, and sells revert unless `block.timestamp > lastTradeTimestamp + SHARE_LOCK_PERIOD` (10 min). `buyShareCredFor` lets an arbitrary caller perform a buy crediting an arbitrary `curator_`, which resets that curator's timestamp. The lock is keyed on the curator, not on who paid.
- Impact: An attacker can grief any shareholder by buying 1 share "for" them every <10 minutes, continually resetting their lock so they can never reach the unlock window and can never sell their existing position. The same reset occurs in the batch buy path (`_executeBatchTrade`).

## Claim signatures / Merkle entries are replayable (no claim-once enforcement)
- Location: `src/PhiFactory.sol` : `_validateAndUpdateClaimState` (used by `signatureClaim` / `merkleClaim`)
- Mechanism: The function sets `artMinted[artId_][minter_] = true` and `credMinted[...] = true` but never *checks* them, and there is no nonce. The interface even defines an `AddressAlreadyMinted` error that is never used. The signed payload for `signatureClaim` (expiresIn, minter, ref, verifier, artId, chainid, data) has no single-use guard, and a Merkle leaf can be proven repeatedly.
- Impact: A single signer-issued signature (until `expiresIn`) or a single Merkle-whitelisted address can mint repeatedly, up to `maxSupply`. This breaks the intended one-claim-per-eligible-address model: a single eligible/authorized address can monopolize the entire supply and repeatedly trigger reward payouts, denying other legitimate claimants.

## Reward-distribution can be sandwiched in CuratorRewardsDistributor
- Location: `src/reward/CuratorRewardsDistributor.sol` : `distribute`
- Mechanism: `distribute` is permissionless and splits the *entire* accumulated `balanceOf[credId]` across holders strictly by their *instantaneous* share balance (`getShareNumber` at call time), with no time-weighting or snapshot. Curate-reward ETH accrues into `balanceOf[credId]` continuously as mints occur.
- Impact: An attacker can buy a large share amount in the same block as (or just before) calling `distribute`, capture a proportional cut of all previously-accumulated rewards, and exit after the 10-minute lock. Because the distribution ignores how long shares were held, this is a profitable MEV/sandwich against honest long-term curators who funded the pool. The caller additionally collects the `royaltyfee` and rounding dust on every call.

## Broken/Out-of-bounds pagination in `getPositionsForCurator`
- Location: `src/Cred.sol` : `getPositionsForCurator`
- Mechanism: The result arrays are allocated with length `stopIndex - start_`, but the loop writes to `credIds[i]`/`amounts[i]` using the raw loop index `i` (which ranges from `start_` to `stopIndex`) rather than a zero-based write cursor. Whenever `start_ > 0`, the first write `credIds[start_]` is past the array's length and reverts; even with `start_ == 0`, the separate `index` counter used for the final `mstore` truncation does not match the `i`-based writes, producing misaligned/sparse output.
- Impact: Paginated reads with any non-zero `start_` always revert, and zero-start reads return positionally incorrect data. This is view-only (no fund loss), but it breaks the contract's documented pagination API and any integrator relying on it.

Note on the unused `nonReentrant` guard on the single `buyShareCred`/`sellShareCred` paths: I checked the ordering and share/supply state is updated before the ETH transfers (CEI is followed), so it is not exploitable as reentrancy — I'm not reporting it as a finding.

