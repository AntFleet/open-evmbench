# Audit: 2024-12-secondswap

I found these genuine vulnerabilities:

## Sold vesting can still be overclaimed by the seller
- Location: `contracts/SecondSwap_StepVesting.sol` : `transferVesting`, `claimable`, `claim`
- Mechanism: When vesting is transferred, `transferVesting` subtracts `_amount` from `grantorVesting.totalAmount` but leaves `amountClaimed` unchanged, then recalculates `releaseRate` as `grantorVesting.totalAmount / numOfSteps`. This uses the full schedule denominator instead of remaining unclaimed tokens over remaining steps. If a user has already claimed some steps and then transfers or lists all remaining unclaimed vesting, their `totalAmount` can become equal to `amountClaimed` while `releaseRate` remains positive. Before the final step, `claimable()` returns `releaseRate * claimableSteps` without capping it to `totalAmount - amountClaimed`.
- Impact: A seller can claim vested tokens, list or sell the remaining allocation, and then continue claiming extra tokens in later steps. This double-spends vesting allocations, drains tokens backing buyers or other beneficiaries, and can corrupt the seller’s vesting state so later claims revert.

## Marketplace escrow merges incompatible vesting schedules
- Location: `contracts/SecondSwap_StepVesting.sol` : `_createVesting`, `transferVesting`; `contracts/SecondSwap_VestingManager.sol` : `listVesting`, `completePurchase`
- Mechanism: The marketplace manager holds all listed vesting for a plan under one address, but `SecondSwap_StepVesting` stores only one `Vesting` struct per address. When the manager already has a vesting balance, `_createVesting()` ignores the incoming `_stepsClaimed` value and merges the new listing into the manager’s existing `stepsClaimed` and `releaseRate`. Purchases then transfer from this aggregated manager position, so buyers inherit the manager’s aggregate vesting progress rather than the seller/listing-specific progress.
- Impact: A buyer can receive purchased vesting with fewer claimed steps than the seller had, allowing immediate claims of tokens that should only vest over future steps. This bypasses the vesting lock and can drain locked token reserves early. The reverse case can also corrupt buyer schedules and deny valid future claims.

## Token issuer can arbitrarily confiscate user vesting
- Location: `contracts/SecondSwap_StepVesting.sol` : `transferVesting`; `contracts/SecondSwap_VestingDeployer.sol` : `transferVesting`
- Mechanism: `SecondSwap_StepVesting.transferVesting()` allows `tokenIssuer`, `manager`, or `vestingDeployer` to transfer vesting from any `_grantor` to any `_beneficiary` without approval from the grantor. `SecondSwap_VestingDeployer.transferVesting()` exposes this to the configured token owner for any grantor in that vesting contract.
- Impact: A token issuer or token owner can move any beneficiary’s unclaimed vesting to themselves or another address, bypassing user consent and marketplace payment. This is a direct vesting confiscation path.

## Private sale whitelist is permissionless
- Location: `contracts/SecondSwap_Whitelist.sol` : `whitelistAddress`; `contracts/SecondSwap_Marketplace.sol` : `_validatePurchase`
- Mechanism: Private listings rely only on `IWhitelist.validateAddress(msg.sender)`, but `SecondSwap_Whitelist.whitelistAddress()` lets any address add itself until `maxWhitelist` is reached. The lot owner cannot curate entries, remove attackers, or restrict who joins.
- Impact: Any attacker can self-whitelist and buy from a private listing. Attackers can also fill all whitelist slots first, blocking intended buyers from participating.

## Invalid vesting parameters can permanently brick claims
- Location: `contracts/SecondSwap_VestingDeployer.sol` : `deployVesting`; `contracts/SecondSwap_StepVesting.sol` : `constructor`, `claimable`
- Mechanism: `deployVesting()` checks `startTime < endTime` and `steps > 0`, but does not require `steps <= endTime - startTime`. In the `SecondSwap_StepVesting` constructor, `stepDuration = (_endTime - _startTime) / _numOfSteps`; if `_numOfSteps` is larger than the duration in seconds, `stepDuration` becomes zero. `claimable()` then divides by `stepDuration`.
- Impact: Every `claim()` for that vesting contract reverts forever due to division by zero, locking deposited vesting tokens.

## Referral rewards are never paid
- Location: `contracts/SecondSwap_Marketplace.sol` : `_handleTransfers`
- Mechanism: `_handleTransfers()` computes `referralFeeCost` when `_referral` is supplied, but never transfers anything to `_referral`. It then sends the full `buyerFeeTotal + sellerFeeTotal` to `feeCollector`. The computed referral amount is only emitted in the event and is not settled.
- Impact: Referrers receive no rewards even when purchases specify a valid referral. The marketplace fee collector captures the entire fee amount, breaking referral accounting and incentives.

