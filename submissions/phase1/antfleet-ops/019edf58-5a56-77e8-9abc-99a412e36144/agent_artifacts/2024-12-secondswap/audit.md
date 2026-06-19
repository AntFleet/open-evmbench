# Audit: 2024-12-secondswap

# Security Audit Report

## Referral Reward Never Distributed
- **Location:** `SecondSwap_Marketplace.sol` : `_handleTransfers`
- **Mechanism:** The function calculates `referralFeeCost` (the portion of the buyer fee owed to the referrer) but never transfers it to the `_referral` address or any `referralFeeCollector`. The buyer pays `baseAmount + buyerFeeTotal` and the fee collector receives the full `buyerFeeTotal + sellerFeeTotal`. The referrer receives nothing despite the `Purchased` event reporting a non-zero `referralReward`.
- **Impact:** The entire referral incentive system is non-functional. Referrers never get paid, and the fee collector silently receives funds intended for referrers. Buyers who participate expecting referral rewards are defrauded of the promised kickback.

## maxSellPercent Bypass via Buy-Sell Cycling
- **Location:** `SecondSwap_VestingManager.sol` : `listVesting`
- **Mechanism:** The sell-limit formula is `sellLimit = bought + ((currentAlloc + sold - bought) * maxSellPercent) / BASE`. The `bought` term means every token bought on the marketplace can be re-sold 100%, and `sold` is a cumulative counter that only decreases on unlist (never when a purchase completes). A user can sell `A` tokens (increasing `sold` by `A`), then buy `A` tokens from another listing (increasing `bought` by `A`), which raises `sellLimit` by exactly `A`, allowing them to sell `A` more. Each cycle, the user dumps `A` real original-vesting tokens to the market while maintaining their balance. Repeating this N times sells `N × A` original tokens, fully bypassing `maxSellPercent`.
- **Impact:** Any vesting holder can circumvent the `maxSellPercent` restriction entirely and dump 100% of their vested tokens, defeating the core purpose of the sell-limit mechanism. This enables large-scale token dumping far beyond the intended cap.

## Incorrect releaseRate After transferVesting Distorts Vesting Schedule
- **Location:** `SecondSwap_StepVesting.sol` : `transferVesting`
- **Mechanism:** After reducing the grantor's `totalAmount`, the release rate is recalculated as `grantorVesting.releaseRate = grantorVesting.totalAmount / numOfSteps`. This does not account for tokens already claimed (`amountClaimed`) or steps already claimed (`stepsClaimed`). The correct formula (used in `_createVesting` for additions) is `(totalAmount - amountClaimed) / (numOfSteps - stepsClaimed)`. By using the full `numOfSteps` and ignoring `amountClaimed`, the release rate is set too high when the grantor has already claimed steps.
- **Impact:** The grantor's vesting schedule is distorted—tokens become claimable earlier than intended (front-loaded). While the total claimable amount is eventually capped by `claimable()`'s end-of-vesting safeguard, the temporal distribution is wrong, allowing grantors to claim tokens ahead of their scheduled release. For beneficiaries receiving transfers, the schedule is correct, but the grantor's remaining schedule is corrupted.
