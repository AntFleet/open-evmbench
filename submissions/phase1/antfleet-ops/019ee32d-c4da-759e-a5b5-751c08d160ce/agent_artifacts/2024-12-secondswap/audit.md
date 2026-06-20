# Audit: 2024-12-secondswap

## Insolvency and Token Inflation via Malformed `releaseRate` Recalculation
- Location: `SecondSwap_StepVesting.sol` : `transferVesting`
- Mechanism: When a grantor transfers a portion of their vested tokens (for example, when listing on the marketplace), the contract decreases `grantorVesting.totalAmount` and recomputes the grantor's future `releaseRate` using `grantorVesting.totalAmount / numOfSteps`. This is mathematically flawed because the grantor has already claimed `stepsClaimed` steps. Spreading the newly reduced `totalAmount` over the full `numOfSteps` (instead of the remaining steps) artificially inflates the future claim rate. Consequently, subsequent intermediate claims will retrieve abnormally large quantities of tokens, leading to `amountClaimed` eventually exceeding the grantor's `totalAmount`.
- Impact: A user can inflate their claimable balance and drain the shared token pool inside the contract, stealing tokens belonging to other users. Additionally, during the final steps, the final claim of the grantor will systematically revert due to mathematical underflow as `totalAmount - amountClaimed` becomes negative, or the contract will become insolvent and block honest claimants from withdrawing.

## Reentrancy in `spotPurchase` Allows Draining of Other Listings' Vesting Tokens
- Location: `SecondSwap_Marketplace.sol` : `spotPurchase`
- Mechanism: The contract executes external ERC20 token transfers through `_handleTransfers` before updating the state variables (`listing.balance` and `listing.status`). If the payment token used by the marketplace implements a transfer hook or callback (such as ERC777 or any custom transfer-callback mechanism), an attacker can reenter `spotPurchase` from the callback. Because the listing's balance has not yet been decremented, the check `require(_amount <= listing.balance)` will repeatedly pass.
- Impact: An attacker can execute multiple purchases from the same listing, buying more than the seller's listed balance. Since the `VestingManager` holds a combined pool of vesting allocations for all sellers of a specific vesting plan, the attacker can force the contract to transfer more vesting tokens than the listing actually contained, draining and stealing the listed allocations belonging to other innocent sellers.

## Whitelist Bypass via Publicly Accessible Self-Whitelisting
- Location: `SecondSwap_Whitelist.sol` : `whitelistAddress`
- Mechanism: The contract deploys a whitelist for private listings using a dedicated whitelist contract. However, the `whitelistAddress` function is marked as `external` and contains absolutely no access control, signatures, or caller verification. Any address can call `whitelistAddress` on any deployed whitelist contract.
- Impact: Private token listings can easily be bypassed by unauthorized users. Malicious actors or front-running bots can self-whitelist and purchase exclusive token allocations that were reserved for specific buyers.

## Referral Reward is Calculated But Never Transferred
- Location: `SecondSwap_Marketplace.sol` : `_handleTransfers`
- Mechanism: In `_handleTransfers`, when a valid referral is provided, the contract calculates `referralFeeCost`. However, the code only performs transfers of the remaining listing price to the seller and the entire sum of `buyerFeeTotal + sellerFeeTotal` to the `feeCollector`. No transaction is coded to transfer the computed `referralFeeCost` to the actual `_referral` address.
- Impact: Referrers do not receive their specified referral rewards on-chain. All funds intended for referral payouts remain with and are sent to the standard `feeCollector`.

## Locked Tokens via Division by Zero on Invalid Step Parameters
- Location: `SecondSwap_VestingDeployer.sol` : `deployVesting` and `SecondSwap_StepVesting.sol` : `constructor`
- Mechanism: The `deployVesting` function does not validate that `endTime - startTime >= steps`. If a user deploys a vesting contract where the step count exceeds the timeline duration (`endTime - startTime < steps`), the integer division `(_endTime - _startTime) / _numOfSteps` in the `SecondSwap_StepVesting` constructor calculates `stepDuration = 0`. Due to this, the `claimable` function (needed for all claims) will always divide `elapsedTime / stepDuration`, resulting in a division-by-zero revert.
- Impact: Deployed vesting schedules under these parameters are permanently bricked. Any tokens transferred from the `tokenIssuer` to the contract during creation are permanently locked and can never be claimed.
