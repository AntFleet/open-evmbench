# Audit: 2023-12-ethereumcreditguild

# Vulnerability Report

After conducting a thorough review of the provided Solidity codebase, several vulnerabilities have been identified. Below, each vulnerability is discussed in detail, including its location, mechanism, and potential impact.

## 1. Unprotected Function in GuildToken

- **Location**: `GuildToken.sol` : `applyGaugeLoss` function
- **Mechanism**: The `applyGaugeLoss` function does not check if the `gauge` parameter is a valid lending term. This allows an attacker to potentially manipulate the gauge weights by applying a loss to an arbitrary address.
- **Impact**: An attacker could exploit this vulnerability to drain the GUILD token balance of unsuspecting users or manipulate the gauge weights, potentially disrupting the lending terms' debt ceilings.

## 2. Reentrancy Vulnerability in LendingTerm

- **Location**: `LendingTerm.sol` : `onBid` function
- **Mechanism**: The `onBid` function calls the `CreditToken.transferFrom` function, which can potentially lead to a reentrancy attack if the `CreditToken` contract is not properly secured.
- **Impact**: An attacker could exploit this vulnerability to drain the CREDIT token balance of the LendingTerm contract or manipulate the loan's state.

## 3. Unsecured Use of `transfer` in LendingTerm

- **Location**: `LendingTerm.sol` : `repay` and `partialRepay` functions
- **Mechanism**: The `repay` and `partialRepay` functions use the `CreditToken.transferFrom` function to pull debt from the borrower. However, if the borrower has not approved the LendingTerm contract to spend their CREDIT tokens, the `transferFrom` function will revert.
- **Impact**: An attacker could exploit this vulnerability to prevent borrowers from repaying their loans, potentially leading to a loss of collateral.

## 4. Potential Front-Running Attack in SimplePSM

- **Location**: `SimplePSM.sol` : `mint` and `redeem` functions
- **Mechanism**: The `mint` and `redeem` functions use the `getMintAmountOut` and `getRedeemAmountOut` functions to calculate the amount of CREDIT tokens to mint or redeem. However, these functions use the current timestamp, which can be manipulated by an attacker using front-running techniques.
- **Impact**: An attacker could exploit this vulnerability to manipulate the amount of CREDIT tokens minted or redeemed, potentially leading to a profit at the expense of other users.

## 5. Missing Access Control in CoreRef

- **Location**: `CoreRef.sol` : `setCore` function
- **Mechanism**: The `setCore` function does not check if the caller is authorized to update the `core` variable.
- **Impact**: An attacker could exploit this vulnerability to update the `core` variable and potentially manipulate the access control of the protocol.

## 6. Unprotected Function in ProfitManager

- **Location**: `ProfitManager.sol` : `notifyPnL` function
- **Mechanism**: The `notifyPnL` function does not check if the caller is authorized to notify profit and loss.
- **Impact**: An attacker could exploit this vulnerability to manipulate the profit and loss of a gauge, potentially leading to a change in the CREDIT token's value.

## 7. Missing Input Validation in LendingTermOnboarding

- **Location**: `LendingTermOnboarding.sol` : `createTerm` function
- **Mechanism**: The `createTerm` function does not validate the input parameters, potentially allowing an attacker to create a lending term with arbitrary parameters.
- **Impact**: An attacker could exploit this vulnerability to create a lending term with parameters that could lead to a loss of collateral or manipulate the gauge weights.

## 8. Reentrancy Vulnerability in AuctionHouse

- **Location**: `AuctionHouse.sol` : `startAuction` function
- **Mechanism**: The `startAuction` function calls the `LendingTerm.getLoan` function, which can potentially lead to a reentrancy attack if the `LendingTerm` contract is not properly secured.
- **Impact**: An attacker could exploit this vulnerability to drain the collateral of the AuctionHouse contract or manipulate the loan's state.

## 9. Unsecured Use of `transfer` in SurplusGuildMinter

- **Location**: `SurplusGuildMinter.sol` : `stake` function
- **Mechanism**: The `stake` function uses the `CreditToken.transferFrom` function to pull CREDIT tokens from the user. However, if the user has not approved the SurplusGuildMinter contract to spend their CREDIT tokens, the `transferFrom` function will revert.
- **Impact**: An attacker could exploit this vulnerability to prevent users from staking their CREDIT tokens, potentially leading to a loss of GUILD token rewards.

## 10. Missing Access Control in RateLimitedMinter

- **Location**: `RateLimitedMinter.sol` : `mint` and `replenishBuffer` functions
- **Mechanism**: The `mint` and `replenishBuffer` functions do not check if the caller is authorized to perform these actions.
- **Impact**: An attacker could exploit this vulnerability to mint or replenish the buffer of CREDIT tokens, potentially leading to a loss of collateral or manipulation of the gauge weights.
