# Audit: 2024-12-secondswap

## 1. Reentrancy Vulnerability in `unlistVesting` Function
- Location: `SecondSwap_Marketplace` : `unlistVesting`
- Mechanism: The `unlistVesting` function is vulnerable to reentrancy attacks because it first checks the conditions and then calls an external contract (`IVestingManager(IMarketplaceSetting(marketplaceSetting).vestingManager()).unlistVesting`). If the contract being called reenters this function, it can potentially drain the contract's funds or cause other unintended behavior.
- Impact: An attacker could exploit this vulnerability to drain the contract's funds or manipulate the vesting listings.

## 2. Unauthorized Access in `setVestingDeployer` Function
- Location: `SecondSwap_VestingManager` : `setVestingDeployer`
- Mechanism: The `setVestingDeployer` function does not restrict access to only the admin or authorized users. This means any user can call this function and update the vesting deployer address, potentially allowing unauthorized control over vesting deployments.
- Impact: An attacker could exploit this vulnerability to take control of the vesting deployer, allowing them to deploy malicious vesting contracts or disrupt the normal functioning of the vesting system.

## 3. Lack of Input Validation in `createVesting` Function
- Location: `SecondSwap_VestingDeployer` : `createVesting`
- Mechanism: The `createVesting` function lacks proper input validation for the `_beneficiary` and `_totalAmount` parameters. This could lead to unintended behavior if these parameters are not validated correctly, such as creating vestings with zero or negative amounts.
- Impact: An attacker could potentially create vestings with invalid or malicious parameters, disrupting the intended functionality of the vesting system.

## 4. Front-Running Vulnerability in `spotPurchase` Function
- Location: `SecondSwap_Marketplace` : `spotPurchase`
- Mechanism: The `spotPurchase` function is vulnerable to front-running attacks because it does not prevent an attacker from observing and reacting to a user's purchase attempt before it is confirmed on the blockchain. An attacker could front-run a purchase by submitting their own purchase transaction with a higher gas price, potentially buying the tokens at a lower price and then selling them at a higher price.
- Impact: An attacker could exploit this vulnerability to profit from front-running legitimate users' purchase attempts.

## 5. Inconsistent Comparison in `whitelistAddress` Function
- Location: `SecondSwap_Whitelist` : `whitelistAddress`
- Mechanism: The `whitelistAddress` function uses inconsistent comparisons (`require(totalWhitelist < maxWhitelist,...)`) without checking if `userSettings[msg.sender]` is already `true`. This could lead to unexpected behavior if the comparison is not as intended.
- Impact: An attacker could exploit this vulnerability by whitelisting an address multiple times, potentially exceeding the maximum whitelist capacity.

## 6. Use of `transfer` and `transferFrom` Functions
- Location: Multiple locations throughout the contracts
- Mechanism: The use of `transfer` and `transferFrom` functions can lead to issues with contract functionality if the recipient contract does not implement the necessary callback functions or if the transfer fails due to insufficient funds.
- Impact: An attacker could exploit this vulnerability by manipulating the transfer process, potentially causing contracts to malfunction or lose funds.

## 7. Insufficient Access Control in `setMaxWhitelist` Function
- Location: `SecondSwap_Whitelist` : `setMaxWhitelist`
- Mechanism: The `setMaxWhitelist` function only checks if the caller is the lot owner but does not restrict the new maximum whitelist capacity to be greater than the current total whitelist count. This could lead to unintended behavior if the maximum capacity is reduced below the current total whitelist count.
- Impact: An attacker could exploit this vulnerability to reduce the maximum whitelist capacity and restrict legitimate users from being whitelisted.

## 8. Claimed Amount Not Checked in `transferVesting` Function
- Location: `SecondSwap_StepVesting` : `transferVesting`
- Mechanism: The `transferVesting` function does not check if the claimed amount has been updated correctly before transferring vesting tokens. This could lead to incorrect vesting balances if the claimed amount is not properly updated.
- Impact: An attacker could exploit this vulnerability to manipulate vesting balances and potentially steal tokens.

## 9. DOS Caused by the Use of `transfer` and `transferFrom` Functions
- Location: Multiple locations throughout the contracts
- Mechanism: The use of `transfer` and `transferFrom` functions can cause denial-of-service (DOS) issues if the recipient contract does not implement the necessary callback functions or if the transfer fails due to insufficient funds.
- Impact: An attacker could exploit this vulnerability to cause DOS attacks, potentially disabling contract functionality.

## 10. Improper Comparison in `whitelistAddress` Function
- Location: `SecondSwap_Whitelist` : `whitelistAddress`
- Mechanism: The `whitelistAddress` function uses an improper comparison (`require(userSettings[msg.sender] == false,...)`) without checking if the user is already whitelisted. This could lead to unexpected behavior if the comparison is not as intended.
- Impact: An attacker could exploit this vulnerability to whitelist an address multiple times, potentially exceeding the maximum whitelist capacity.

## 11. Inefficient `_listingType` Check
- Location: `SecondSwap_Marketplace` : `listVesting`
- Mechanism: The `_listingType` check in the `listVesting` function is inefficient and could lead to unintended behavior if the listing type is not correctly validated.
- Impact: An attacker could exploit this vulnerability to create listings with invalid or malicious parameters, disrupting the intended functionality of the marketplace.

## 12. Rounding Issue Leads to Total Drain of Vesting Entries
- Location: `SecondSwap_Marketplace` : `listVesting` and `spotPurchase`
- Mechanism: The use of integer division and multiplication in the `listVesting` and `spotPurchase` functions can lead to rounding issues, potentially causing the total drain of vesting entries.
- Impact: An attacker could exploit this vulnerability to drain the vesting entries, potentially stealing tokens.

## 13. The `s2Admin` is Unable to Unlist Vesting
- Location: `SecondSwap_Marketplace` : `unlistVesting`
- Mechanism: The `unlistVesting` function does not allow the `s2Admin` to unlist vesting, potentially limiting the admin's control over the marketplace.
- Impact: An attacker could exploit this vulnerability to prevent the admin from unlisting vesting, potentially disrupting the marketplace's functionality.

## 14. Buyer Can Choose Listing Price
- Location: `SecondSwap_Marketplace` : `unlistVesting` and `spotPurchase`
- Mechanism: The `unlistVesting` and `spotPurchase` functions do not restrict the buyer's ability to choose the listing price, potentially allowing them to manipulate the marketplace.
- Impact: An attacker could exploit this vulnerability to manipulate the marketplace prices, potentially stealing tokens or disrupting the marketplace's functionality.

## 15. Value Difference Caused by the Same Penalty Fee
- Location: `SecondSwap_Marketplace` : `unlistVesting`
- Mechanism: The use of the same penalty fee in the `unlistVesting` function can lead to value differences, potentially causing unintended behavior.
- Impact: An attacker could exploit this vulnerability to manipulate the penalty fee, potentially stealing tokens or disrupting the marketplace's functionality.
