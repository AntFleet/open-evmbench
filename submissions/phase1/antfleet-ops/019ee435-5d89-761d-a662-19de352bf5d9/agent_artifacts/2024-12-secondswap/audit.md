# Audit: 2024-12-secondswap

## Private whitelists are publicly joinable
- Location: `contracts/SecondSwap_Whitelist.sol` : `whitelistAddress`
- Mechanism: Private marketplace listings rely on `IWhitelist.validateAddress(msg.sender)`, but the whitelist contract lets any address call `whitelistAddress()` and add itself until `maxWhitelist` is reached. The `lotOwner` cannot curate, remove, or approve addresses; they can only increase the cap.
- Impact: Any attacker can self-whitelist and buy from a “private” listing. Attackers can also fill all whitelist slots first, blocking intended buyers and forcing the seller to increase capacity.

## Vesting transfer merges schedules and can unlock tokens early
- Location: `contracts/SecondSwap_StepVesting.sol` : `transferVesting`, `_createVesting`
- Mechanism: Each address has a single `Vesting` struct, but transferred vesting lots may have different `stepsClaimed`. When the beneficiary already has a vesting entry, `_createVesting` ignores the incoming `_stepsClaimed` and recalculates one blended `releaseRate`. The marketplace manager address also acts as a shared intermediate holder, so listings from sellers with different claimed-step histories are merged into one manager vesting state before resale.
- Impact: Buyers can receive future-only vesting with an older/lower `stepsClaimed` value and claim tokens earlier than the original schedule permits. This breaks vesting lock guarantees and can accelerate circulating supply for allocations sold through the marketplace.

## Invalid vesting step configuration can make claims permanently revert
- Location: `contracts/SecondSwap_VestingDeployer.sol` : `deployVesting`; `contracts/SecondSwap_StepVesting.sol` : `constructor`, `claimable`
- Mechanism: `deployVesting` only checks `startTime < endTime` and `steps > 0`. If `steps > endTime - startTime`, the constructor computes `stepDuration = (_endTime - _startTime) / _numOfSteps`, which becomes zero. `claimable()` later divides by `stepDuration`, so every claim after `startTime` reverts.
- Impact: A malicious or careless token issuer can create vesting allocations that appear valid and can be listed/sold, but buyers and beneficiaries can never claim the underlying tokens.

## Referral rewards are never paid
- Location: `contracts/SecondSwap_Marketplace.sol` : `_handleTransfers`
- Mechanism: `_handleTransfers` computes `referralFeeCost` when `_referral` is set, but never transfers any tokens to `_referral`. It then sends the full `buyerFeeTotal + sellerFeeTotal` to `feeCollector`. The emitted `Purchased` event can report a nonzero referral value even though no referral payment occurred.
- Impact: Referrers receive no on-chain reward despite the marketplace accepting referral addresses and emitting referral accounting. The fee collector receives funds that should have been allocated to referral rewards.

