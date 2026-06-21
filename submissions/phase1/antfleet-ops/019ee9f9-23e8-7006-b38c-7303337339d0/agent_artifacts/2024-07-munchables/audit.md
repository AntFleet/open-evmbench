# Audit: 2024-07-munchables

# Munchables Security Audit Report

## Schnibble inflation via incorrect scaling in `pet`
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: `PET_TOTAL_SCHNIBBLES` is already configured on a 1e18 scale (`10e18 / 72`), and `totalSchnibbles` is derived from that value. The payout lines then multiply the 5/11 and 6/11 splits by an additional `1e18`, applying the wei scaling twice. Each pet interaction mints schnibbles on the order of `~1e34` instead of the intended `~1e17` range.
- Impact: Any registered user can repeatedly pet other players’ munchables and inflate `unfedSchnibbles` to absurd balances, breaking all schnibble-based game economics (feeding, primordials, harvest weighting) and enabling downstream value extraction wherever schnibbles convert into points or other assets.

## Lock remainder destroyed on partial unlock
- Location: `src/managers/LockManager.sol` : `unlock`
- Mechanism: Locking accumulates a `remainder` when deposited amounts do not evenly divide `nftCost`; that remainder is carried into the next lock to count toward future NFT entitlement. On unlock, the function decrements `quantity` but unconditionally sets `remainder = 0`, discarding any accumulated fractional progress without crediting NFTs or refunding its value.
- Impact: A user who partially unlocks before their lock period ends permanently loses credit toward unrevealed NFTs they already paid for, resulting in direct economic loss relative to the lockdrop rules.

## Permissionless protocol yield and gas claiming
- Location: `src/managers/RewardsManager.sol` : `claimYieldForContracts`, `claimGasFeeForContracts`
- Mechanism: Both functions are `external` with no role or caller restriction. Any address may pass an arbitrary list of protocol contract addresses and trigger Blast yield/gas harvesting through `RewardsManager`, which then forwards proceeds to configured distributors.
- Impact: While proceeds are routed to treasury distributors rather than the caller’s wallet, any third party can force harvesting timing on protocol contracts, claim gas/yield without authorization, and potentially grief accounting, monitoring, or operational assumptions about when rewards are collected. If distributor configuration or forwarded-token handling is ever misconfigured, this open entrypoint expands blast radius.

## Every new lock resets unlock timer
- Location: `src/managers/LockManager.sol` : `_lock`
- Mechanism: Each lock operation sets `unlockTime = block.timestamp + lockDuration`, regardless of how much time remains on an existing lock. Additional deposits therefore reset the full lock countdown from zero rather than preserving or extending the prior unlock deadline.
- Impact: Users who add funds incrementally are forced into a longer total lock than they may expect, and anyone who deposits again near the end of a lock period has their withdrawal delayed by the entire duration again. This can trap liquidity longer than the stated lock-duration semantics imply.

## Off-by-one bypass of staked-munchable limit
- Location: `src/managers/LandManager.sol` : `stakeMunchable`
- Mechanism: The contract rejects staking only when `munchablesStaked[mainAccount].length > 10`. When length is exactly `10`, the check passes and an 11th munchable is pushed.
- Impact: Players can stake one more munchable than the intended maximum of 10, gaining extra farming income and landlord-tax interactions beyond the protocol’s stated cap.

## Claim period consumed with zero payout
- Location: `src/managers/ClaimManager.sol` : `_claimPoints`
- Mechanism: At the end of `_claimPoints`, `_lastClaimPeriod[_player]` is always set to the current period ID even when `claimAmount` is `0` (for example, when the player has no chonk at the time of the call). The early-return path for zero rewards still advances the claim marker.
- Impact: A player whose first period interaction occurs before they have chonk (via `forceClaimPoints` from `SnuggeryManager`’s `chonkUpdated` modifier) marks the period as claimed without receiving points, and cannot claim again until the next period starts. This causes loss of emissions they would otherwise earn after importing or feeding munchables later in the same period.

