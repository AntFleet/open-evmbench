# Audit: 2024-12-secondswap

**Reentrancy in purchase flow allowing multiple purchases or state manipulation**

- Location: contracts/SecondSwap_Marketplace.sol : spotPurchase (via _handleTransfers)
- Mechanism: spotPurchase calls _validatePurchase then _handleTransfers (which performs IERC20.safeTransferFrom from buyer + safeTransfer to seller/feeCollector) before the subsequent `listing.balance -= _amount` and status update. No reentrancy guard exists and the currency token can contain arbitrary logic on transfer.
- Impact: Malicious currency token can re-enter spotPurchase (or other payable functions) to buy the same listing multiple times, exceed the remaining balance, or bypass discount/fee logic before state is finalized.

**Admin unlisting bypasses seller checks but still operates on original seller vesting**

- Location: contracts/SecondSwap_Marketplace.sol : unlistVesting
- Mechanism: When `msg.sender == s2Admin`, the function skips the penalty check and time check, then unconditionally calls `unlistVesting(listing.seller, ...)` and sets DELIST/zero balance. No separate admin-only path or ownership transfer exists.
- Impact: Admin can forcibly delist any active listing belonging to any seller and return the remaining tokens to that seller (or grief listings) without the seller's involvement or penalty.

**Rounding-to-zero in price math allows blocked but potentially bypassable zero-cost listings/purchases**

- Location: contracts/SecondSwap_Marketplace.sol : listVesting and _handleTransfers (also _getDiscountedPrice)
- Mechanism: `baseAmount = (_amount * price) / 10**decimals()` (and same after LINEAR/FIX discount) followed by `require(baseAmount > 0)`. Discounts can drive the result to zero for small amounts or high decimals, and the check occurs after vesting manager interaction.
- Impact: Attacker can create listings (or attempt purchases) that round to zero payment, causing reverts after partial state changes or forcing the marketplace into inconsistent states when combined with SINGLE listing type or low-balance edge cases.

**Missing check allows admin to unlist without updating seller allocation correctly in some paths**

- Location: contracts/SecondSwap_Marketplace.sol : unlistVesting (cross-referenced with VestingManager.unlistVesting)
- Mechanism: Admin path skips penalty transfer but still executes the vesting manager call using the original `listing.seller`; no separate accounting adjustment for admin-initiated unlist.
- Impact: Seller allocation state in VestingManager can become inconsistent with actual token location when admin performs early unlists.

**Whitelist self-registration comparison and limit check can be bypassed under concurrent calls**

- Location: contracts/SecondSwap_Whitelist.sol : whitelistAddress
- Mechanism: `require(totalWhitelist < maxWhitelist)` then `require(userSettings[msg.sender] == false)` followed by increment and set. No mutex or CEI pattern; multiple calls in same block/tx can pass checks before writes.
- Impact: More addresses than `_maxWhitelist` can be registered, or a single address can be double-counted, breaking private-sale access control.

**Arbitrary vesting creation/transfer via token owner mapping without proper validation**

- Location: contracts/SecondSwap_VestingDeployer.sol : createVesting / transferVesting / deployVesting (and setTokenOwner)
- Mechanism: `require(_tokenOwner[msg.sender] == address(StepVesting(_stepVesting).token()))` trusts the caller-supplied `_stepVesting` address and the stored mapping; no verification that the vesting contract was deployed by the deployer or that the token matches the expected issuer.
- Impact: Attacker who controls a token owner mapping entry can create or transfer arbitrary vesting schedules on unrelated StepVesting contracts, draining or misallocating tokens.
