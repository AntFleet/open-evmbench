# Audit: 2024-12-secondswap

## Reentrancy in `spotPurchase` allows draining of listing tokens
- Location: `SecondSwap_Marketplace.sol` : `spotPurchase`
- Mechanism: The function calls `_handleTransfers` (which performs external token transfers via `safeTransferFrom` and `safeTransfer`) **before** updating `listing.balance` and `listing.status`. If the payment token is a malicious ERC20 that re‑enters `spotPurchase` during a transfer, the `_validatePurchase` check will see the original, unreduced `balance`, allowing the attacker to buy the same tokens multiple times.
- Impact: An attacker can drain the entire remaining balance of a listing, stealing tokens while paying only once.

## Token owner can arbitrarily steal any user’s vested tokens
- Location: `SecondSwap_VestingDeployer.sol` : `transferVesting`
- Mechanism: The `transferVesting` function in `SecondSwap_VestingDeployer` allows the token owner (set by admin) to call `SecondSwap_StepVesting.transferVesting` with arbitrary `_grantor` and `_beneficiary`. The `StepVesting` contract trusts the `vestingDeployer` as an authorized caller. Because the token owner controls the deployer, they can invoke `transferVesting` to move any user’s vesting allocation to themselves without the grantor’s consent.
- Impact: The token owner can steal **all** vested tokens from any user, leading to a complete loss of funds for every vesting beneficiary.

## Referral rewards are never paid
- Location: `SecondSwap_Marketplace.sol` : `_handleTransfers`
- Mechanism: The function computes `referralFeeCost` but never transfers tokens to the referrer. All buyer and seller fees are sent to the `feeCollector`, and the referral reward is simply ignored. The `referralFeeCost` is returned only to be included in the `Purchased` event, but no actual payment occurs.
- Impact: Referrers receive no rewards. The fee collector effectively pockets the referral portion, while the protocol’s referral incentive is broken and users lose expected income.

## Unchecked token addition can permanently brick marketplace operations
- Location: `SecondSwap_Marketplace.sol` : `addCoin`
- Mechanism: `addCoin` sets `isTokenSupport[_token] = true` without verifying that the token implements the `decimals()` function. The marketplace relies on `decimals()` to compute `baseAmount` in `listVesting` and `_handleTransfers`. If a token without `decimals()` is added, any listing or purchase using that token will revert, causing a denial of service.
- Impact: Once such a token is added as a supported currency, the marketplace becomes unusable for that token, and all existing listings denominated in that token are permanently blocked.
