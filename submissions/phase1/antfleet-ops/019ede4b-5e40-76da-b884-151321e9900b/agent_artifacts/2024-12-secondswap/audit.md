# Audit: 2024-12-secondswap

## Missing Referral Reward Transfer
- Location: `SecondSwap_Marketplace.sol` : `_handleTransfers`
- Mechanism: The function calculates the `referralFeeCost` (the portion of the buyer fee intended to be paid to the referrer) but never executes a token transfer to the `_referral` address. Instead, the entire `buyerFeeTotal` is aggregated into `feeCollectorTotal` and sent exclusively to the protocol's `feeCollector`.
- Impact: Referrers never receive their promised rewards for bringing in buyers. The protocol retains the entire buyer fee, effectively cheating referrers out of their earnings and completely breaking the referral incentive mechanism.

## Incorrect Release Rate Calculation Locks Vested Tokens
- Location: `SecondSwap_StepVesting.sol` : `transferVesting`
- Mechanism: When a grantor transfers a portion of their vesting allocation, the contract recalculates the grantor's `releaseRate` by dividing the new `totalAmount` by the total `numOfSteps`. It fails to account for the steps already claimed (`stepsClaimed`) and the amount already claimed (`amountClaimed`). The correct formula should divide the remaining unclaimed amount by the remaining unclaimed steps (as correctly implemented in `_createVesting`).
- Impact: The grantor's `releaseRate` is artificially reduced after a transfer. This locks a significant portion of their remaining vested tokens until the very end of the vesting period (when the `endTime` fallback in the `claimable` function triggers), breaking the step-vesting schedule and causing severe liquidity delays for the user.

## Division by Zero in Vesting Transfer to New Beneficiaries
- Location: `SecondSwap_StepVesting.sol` : `_createVesting`
- Mechanism: When creating a new vesting entry for a beneficiary who currently has a `totalAmount` of 0, the contract calculates `releaseRate` as `_totalAmount / (numOfSteps - _stepsClaimed)`. If the `_stepsClaimed` passed from the grantor equals `numOfSteps` (which can happen if the grantor has fully stepped through their vesting schedule but has dust tokens remaining due to rounding down in previous claims), this results in a division by zero.
- Impact: The transaction will revert, preventing the transfer of dust amounts to new beneficiaries who have not previously received vesting. This causes a denial of service for specific edge-case transfers.

## Check-Effects-Interactions Violation in Spot Purchase
- Location: `SecondSwap_Marketplace.sol` : `spotPurchase`
- Mechanism: The function updates the `listing.balance` and `listing.status` state variables *after* executing external token transfers via `_handleTransfers`. If the `currency` token implements callbacks (e.g., ERC-777 or tokens with transfer hooks), an attacker could re-enter the contract before the listing state is updated.
- Impact: An attacker could exploit the stale listing state to re-enter `spotPurchase` and purchase more tokens than actually available, bypassing the `_amount <= listing.balance` validation check in `_validatePurchase`, potentially leading to unauthorized token extraction or accounting desynchronization.
