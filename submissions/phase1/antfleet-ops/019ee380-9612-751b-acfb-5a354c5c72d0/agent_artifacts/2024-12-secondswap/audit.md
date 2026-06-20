# Audit: 2024-12-secondswap

Below are the genuine security vulnerabilities I found in the SecondSwap contracts. I've excluded the `// 3.x` annotation comments where the underlying flaw is not actually present, and focused on exploitable logic/accounting/access-control/reentrancy issues.

## Referral reward is computed and emitted but never paid

- Location: `SecondSwap_Marketplace.sol` : `_handleTransfers`
- Mechanism: When a valid `_referral` is supplied, the function computes `referralFeeCost` (the portion of the buyer fee that should go to the referrer) and returns/emits it. However, the actual transfers send `baseAmount - sellerFeeTotal` to the seller and the **entire** `feeCollectorTotal = buyerFeeTotal + sellerFeeTotal` to the fee collector. There is no `safeTransfer` to `_referral` anywhere. The referrer therefore receives nothing while the fee collector receives the full buyer fee (including the slice that was supposedly carved out for the referrer).
- Impact: The referral program is non-functional; referrers are never compensated despite the `Purchased` event reporting a `referralReward`. Off-chain systems trusting the emitted `referralReward` will credit rewards that the contract never disbursed, creating an accounting discrepancy.

## Truncation in `baseAmount` lets buyers underpay and drain a listing

- Location: `SecondSwap_Marketplace.sol` : `_handleTransfers` / `spotPurchase` (and mirrored in `listVesting`)
- Mechanism: `baseAmount = (_amount * discountedPrice) / 10**decimals`. With high-decimals vesting tokens and a modest `pricePerUnit`, a buyer can choose `_amount` values (e.g. just under an integer multiple of `10**decimals`) so that the integer division truncates a large fraction of the cost away. The only guard is `require(baseAmount > 0)`, which merely forces each purchase to pay at least 1 base unit; it does not prevent systematically buying token quantities whose fractional value is rounded off. For PARTIAL listings `minPurchaseAmt` can be 0, so the buyer can repeat this in many small purchases.
- Impact: A buyer acquires more vested tokens than they pay for (up to ~2x per call in the worst case, repeated), draining the seller's listed vesting position at a steep effective discount and shortchanging seller + fee collector.

## Reentrancy: listing state updated after external token transfers

- Location: `SecondSwap_Marketplace.sol` : `spotPurchase` (and `unlistVesting`)
- Mechanism: `spotPurchase` performs all currency `safeTransferFrom`/`safeTransfer` calls inside `_handleTransfers` **before** it decrements `listing.balance` and updates `listing.status`. `_validatePurchase` checks `_amount <= listing.balance` against the not-yet-decremented balance. There is no reentrancy guard. If the supported `currency` token has a transfer hook/callback (ERC777-style, or any token an admin whitelists via `addCoin`, which performs no validation), a buyer can re-enter `spotPurchase` during one of the transfers and pass `_validatePurchase` again against stale `balance`, purchasing more than the listing holds. The same CEI violation exists in `unlistVesting`, where `status`/`balance` are zeroed only after the external `unlistVesting` call.
- Impact: Over-purchase beyond `listing.balance` / double-processing, leading to incorrect vesting transfers and loss of seller funds. Severity is gated on the currency token's behavior, but `addCoin` deliberately skips all token validation, so a hooked token can be enabled.

## Token issuer / manager can transfer any beneficiary's vesting (arbitrary `_grantor`)

- Location: `SecondSwap_StepVesting.sol` : `transferVesting`
- Mechanism: `transferVesting(_grantor, _beneficiary, _amount)` is callable when `msg.sender == tokenIssuer || manager || vestingDeployer`, and `_grantor` is fully attacker-chosen. `tokenIssuer` is set to `msg.sender` of `deployVesting` (the token owner). Nothing restricts the `tokenIssuer` from specifying an arbitrary `_grantor`, so the token owner can move any holder's vested allocation to any address. The `VestingDeployer` wrapper attempts an ownership check, but the `StepVesting` contract itself still trusts `tokenIssuer`/`manager` directly with an unrestricted `_grantor`.
- Impact: The token issuer can seize/rug the vested balances of every beneficiary of that vesting contract — full theft of user vesting positions.

## Unprotected `initialize` on proxy-deployed contracts

- Location: `SecondSwap_Marketplace.sol` : `initialize`; `SecondSwap_VestingManager.sol` : `initialize`; `SecondSwap_VestingDeployer.sol` : `initialize`
- Mechanism: These contracts are deployed behind `TransparentUpgradeableProxy` and use the `initializer` modifier, but `initialize` has no access control and the implementations never call `_disableInitializers()`. If the proxy is not initialized atomically in the same transaction as deployment, an attacker can front-run the initialization call and set `marketplaceSetting`/supported token (Marketplace) or `s2Admin`/`manager` (VestingManager, VestingDeployer) to attacker-controlled values.
- Impact: Hostile takeover of the admin/configuration of the marketplace and vesting subsystem (e.g., setting `s2Admin` to the attacker), enabling control over fees, sellable status, and vesting management.

## `transferVesting` recomputes `releaseRate` incorrectly for the grantor

- Location: `SecondSwap_StepVesting.sol` : `transferVesting`
- Mechanism: After reducing the grantor's `totalAmount`, it sets `grantorVesting.releaseRate = grantorVesting.totalAmount / numOfSteps`, dividing by the full `numOfSteps` and ignoring `stepsClaimed` and `amountClaimed`. The correct remaining-schedule rate is `(totalAmount - amountClaimed) / (numOfSteps - stepsClaimed)`. When the grantor has already claimed some steps, the per-step release becomes inconsistent with the actual remaining steps and remaining balance.
- Impact: The grantor's claim schedule is corrupted after a transfer — per-step releases are mis-sized relative to the remaining vesting window. While the final-step cap in `claimable` bounds total claims to `totalAmount - amountClaimed`, the intermediate release amounts no longer match the intended vesting curve, producing incorrect token release timing for any partially-claimed position.

---

Note: the in-code `// 3.x` comments (e.g., the penalty-fee, `whitelistAddress` comparison, and `s2Admin` unlist annotations) were reviewed; those specific code paths appear handled in the present version and I did not find an exploitable flaw in them, so I have not padded the report with them. The `TestToken1` (USDT mock) has a permissionless `mint`, but it is clearly a test fixture, not a protocol contract.

