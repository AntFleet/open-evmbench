# Audit: 2024-12-secondswap

## Truncating price division lets buyers underpay and acquire listed tokens below value
- Location: contracts/SecondSwap_Marketplace.sol : `_handleTransfers` (same pattern in `listVesting`)
- Mechanism: `baseAmount = (_amount * discountedPrice) / 10**vestedTokenDecimals` uses flooring division with only a `require(baseAmount > 0)` guard. A buyer of a PARTIAL listing (which may have `minPurchaseAmt == 0`) can pick `_amount` so that `_amount * discountedPrice` lands just under a multiple of `10**decimals` — e.g. just under `2 * 10**decimals` — making `baseAmount` floor to `1` while the fair cost was ~`2`. Because `buyerFeeTotal`/`sellerFeeTotal` are then computed as `baseAmount * fee / BASE`, with `baseAmount == 1` and `fee == 250` they also truncate to `0`. The buyer repeats the purchase to sweep the whole `listing.balance`.
- Impact: For listings whose per-unit price is small relative to `10**decimals` (low-priced or high-decimal vested tokens), a buyer drains the seller's listed vesting at up to ~50% below the listed price while paying zero protocol/seller fees.

## tokenIssuer can move any grantor's vesting, including the marketplace escrow
- Location: contracts/SecondSwap_StepVesting.sol : `transferVesting` (reachable via contracts/SecondSwap_VestingDeployer.sol : `transferVesting`)
- Mechanism: `transferVesting(address _grantor, address _beneficiary, uint256 _amount)` authorizes `tokenIssuer || manager || vestingDeployer` but lets the caller name an arbitrary `_grantor`. The only constraint is `grantorVesting.totalAmount - grantorVesting.amountClaimed >= _amount`. When tokens are listed, `SecondSwap_VestingManager.listVesting` escrows them as `_vestings[manager]` inside the StepVesting contract. A token issuer can therefore call `transferVesting(manager, attacker, escrowAmount)` (or `transferVesting(victimBeneficiary, attacker, ...)`) and pull tokens out of the escrow / any user's allocation without that party's consent; the VestingManager's `allocations` bookkeeping is never updated, so subsequent `completePurchase` calls then revert.
- Impact: The token issuer (a party the secondary marketplace does not assume to be honest toward sellers) can steal every seller's escrowed listing for that vesting plan and confiscate any beneficiary's vested allocation outright.

## Full-amount payouts make fee-on-transfer currencies drain the contract; transfers precede state updates
- Location: contracts/SecondSwap_Marketplace.sol : `_handleTransfers` / `spotPurchase`
- Mechanism: `_handleTransfers` pulls `baseAmount + buyerFeeTotal` from the buyer, then unconditionally pays `baseAmount - sellerFeeTotal` to the seller and `buyerFeeTotal + sellerFeeTotal` to the fee collector, assuming the contract actually received the full pulled amount. `addCoin` does no validation (the decimals/quirk checks are commented out), so an admin-listed fee-on-transfer token causes the contract to receive less than it pays out, covering the shortfall from other users' balances. Separately, all three `safeTransfer*` calls happen before `listing.balance -= _amount` and before `completePurchase`, with no reentrancy guard, so a hooked (ERC-777-style) currency hands control to the buyer/seller mid-purchase against stale `listing.balance`/`status`.
- Impact: A supported fee-on-transfer currency silently drains pooled marketplace funds over successive purchases, and the lack of CEI ordering exposes the commingled per-plan escrow to reentrancy with callback-bearing payment tokens.

## Unprotected initializers permit admin takeover of the proxies
- Location: contracts/SecondSwap_VestingManager.sol : `initialize` (also contracts/SecondSwap_VestingDeployer.sol : `initialize`, contracts/SecondSwap_Marketplace.sol : `initialize`)
- Mechanism: These `public initializer` functions set the privileged `s2Admin` / `manager` / `marketplaceSetting` slots with no access-control on the caller, and the implementations have no constructor calling `_disableInitializers()`. If the proxy is deployed and initialized in separate transactions (or the implementation is initialized directly), an attacker front-runs the call.
- Impact: A front-runner becomes `s2Admin`/`manager` (VestingManager → controls sellable flags, fees, marketplace address) or points the marketplace at an attacker-controlled settings contract, seizing administrative control of the protocol.

## Referral reward is computed and emitted but never transferred
- Location: contracts/SecondSwap_Marketplace.sol : `_handleTransfers`
- Mechanism: `referralFeeCost` is calculated for a valid `_referral`, but the function only transfers to `listing.seller` and to `feeCollector` (the latter receiving the entire `buyerFeeTotal + sellerFeeTotal`); no transfer is ever made to the referrer. The `Purchased` event nonetheless reports `referralReward = referralFeeCost`, a value no address actually receives.
- Impact: Referrers are never paid despite the advertised incentive, and the referral's share is silently captured by the fee collector — an accounting discrepancy between emitted rewards and actual fund flows.

## setTokenOwner allows many owners per token and never checks the token
- Location: contracts/SecondSwap_VestingDeployer.sol : `setTokenOwner`
- Mechanism: The mapping is keyed by owner (`_tokenOwner[_owner] = token`) and the guard only checks `_tokenOwner[_owner] == address(0)`. It never verifies whether `token` already has an owner, so the admin can map the same token to multiple distinct owner addresses; each then satisfies the `_tokenOwner[msg.sender] == token` check used by `deployVesting`/`createVesting`/`transferVesting`.
- Impact: Multiple addresses can act as the "token owner" for one token, widening the set of accounts that can exercise the arbitrary-`_grantor` `transferVesting` path above and thereby reach the escrow/allocation theft.

