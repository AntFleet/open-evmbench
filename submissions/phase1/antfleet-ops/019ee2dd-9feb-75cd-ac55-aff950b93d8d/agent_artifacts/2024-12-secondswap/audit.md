# Audit: 2024-12-secondswap

 Here is the audit report of the codebase.

## Reentrancy in `spotPurchase` via payment-token callbacks

- Location: `SecondSwap_Marketplace.sol` : `spotPurchase` / `_handleTransfers`
- Mechanism: `spotPurchase` performs external ERC20 transfers inside `_handleTransfers` (both `safeTransferFrom` from the buyer and `safeTransfer` to the seller) before it updates `listing.balance` and `listing.status`. If the payment currency is an ERC777-style token or any ERC20 that executes a receiver hook, the buyer or seller can reenter `spotPurchase` while the listing still shows its original balance. The reentrant call passes `_validatePurchase` because the listing state has not yet been reduced, allowing the same tokens to be sold multiple times before the outer call finishes.
- Impact: A malicious buyer/seller contract can purchase more tokens than the listing balance should allow, causing the seller to receive multiple payments or the contract to over-transfer vesting allocations.

## Referral reward is calculated but never transferred

- Location: `SecondSwap_Marketplace.sol` : `_handleTransfers`
- Mechanism: The function computes `referralFeeCost` as the portion of `buyerFeeTotal` that should be paid to `_referral`, but it never executes a transfer to `_referral`. The full `buyerFeeTotal + sellerFeeTotal` is then sent to `feeCollector`. Because the referrer receives nothing while the event reports a reward, the fee accounting diverges from the intended design.
- Impact: Referrers are systematically denied their rewards; all referral-bound fees are captured by the fee collector instead.

## Incorrect `releaseRate` recalculation in `transferVesting` enables over-claiming

- Location: `SecondSwap_StepVesting.sol` : `transferVesting` / `_createVesting`
- Mechanism: When part of a vesting is transferred, the grantor's `releaseRate` is reset to `grantorVesting.totalAmount / numOfSteps` instead of `(totalAmount - amountClaimed) / (numOfSteps - stepsClaimed)`. Since `amountClaimed` is not reduced, the new rate overstates the tokens still claimable per step. `_createVesting` for the recipient uses the same wrong denominator, but the grantor side is the one that becomes overstated.
- Impact: A user who has claimed some tokens and then transfers part of the remaining allocation can subsequently claim more tokens than they actually own, draining tokens from other beneficiaries or the issuer.

## Unbounded listing discount allows zero-price sales

- Location: `SecondSwap_Marketplace.sol` : `listVesting`
- Mechanism: `listVesting` validates that `_discountPct > 0` when a discount is enabled but never enforces `_discountPct <= BASE`. With `DiscountType.FIX`, setting `_discountPct == BASE` makes `_getDiscountedPrice` return zero. With `DiscountType.LINEAR`, setting `_discountPct == BASE` and purchasing the full listing also drives the effective price to zero.
- Impact: A seller can accidentally or maliciously list tokens at a 100% discount, causing buyers to receive vested tokens for free (paying only zero fees); values above `BASE` cause every purchase to revert, creating unusable listings.

## Fully-claimed vesting transfers can underflow

- Location: `SecondSwap_StepVesting.sol` : `_createVesting` (called from `transferVesting`)
- Mechanism: `claimable` can return a `claimableSteps` larger than `numOfSteps - stepsClaimed` when `block.timestamp` is well past `endTime`, and `claim()` adds that value directly to `stepsClaimed`. Later, `transferVesting` passes that inflated `stepsClaimed` into `_createVesting(..., true)`, which computes `_totalAmount / (numOfSteps - _stepsClaimed)`. If `_stepsClaimed >= numOfSteps`, the subtraction underflows and reverts in Solidity 0.8.
- Impact: After a beneficiary fully claims past the schedule end, their vesting can no longer be transferred, blocking `unlistVesting`, `completePurchase`, or any other `transferVesting` call involving that user.

## Missing storage gap in upgradeable contracts

- Location: `SecondSwap_Marketplace.sol`, `SecondSwap_VestingDeployer.sol`
- Mechanism: Both contracts inherit `Initializable` and are intended to be used behind proxies, but neither declares a `uint256[50] private __gap` array at the end of its storage layout. Without a gap, any future upgrade that appends new state variables will overwrite the storage slots of deployed contracts.
- Impact: A planned upgrade can silently corrupt existing storage, leading to incorrect admin addresses, settings, or listing data.

## Inverted owner-token mapping in `VestingDeployer`

- Location: `SecondSwap_VestingDeployer.sol` : `setTokenOwner`
- Mechanism: The function is named and documented as mapping a token to its owner, but it stores `_tokenOwner[_owner] = token` (owner → token). It checks only that the owner is not already mapped, not that the token is not already owned by someone else.
- Impact: Multiple owners can be associated with the same token, allowing any of them to deploy vesting contracts, create vestings, or transfer vesting entries for that token despite the access-control intent.
