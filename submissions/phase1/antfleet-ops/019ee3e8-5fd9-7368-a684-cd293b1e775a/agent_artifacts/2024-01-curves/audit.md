# Audit: 2024-01-curves

### Reentrancy Vulnerability in `_transferFees`
- Location: `contracts/Curves.sol` : `_transferFees`
- Mechanism: The `_transferFees` function is vulnerable to reentrancy because it first performs calculations to update the state, then calls external contracts to transfer funds. Specifically, it calls `firstDestination.call{value: isBuy? buyValue : sellValue}("")`, `curvesTokenSubject.call{value: subjectFee}("")`, and `referralFeeDestination[curvesTokenSubject].call{value: referralFee}("")`. An attacker could exploit this by causing one of these contract calls to reenter the contract, potentially draining funds without updating the state correctly.
- Impact: An attacker could drain funds from the contract by reentering the contract, causing `transferFees` to transfer more funds than intended.

### Unprotected Function `buyCurvesTokenForPresale`
- Location: `contracts/Curves.sol` : `buyCurvesTokenForPresale`
- Mechanism: The `buyCurvesTokenForPresale` function can be called by anyone, without checking if the caller is authorized to set the presale metadata for the given `curvesTokenSubject`. This allows an attacker to potentially interfere with legitimate presales by setting arbitrary presale metadata.
- Impact: An attacker could manipulate presale metadata, potentially disrupting legitimate presales or allowing unauthorized token purchases.

### Lack of Input Validation in `setFeeRedistributor`
- Location: `contracts/Curves.sol` : `setFeeRedistributor`
- Mechanism: The `setFeeRedistributor` function does not check if the provided `feeRedistributor_` address is valid or if it points to a contract that implements the expected interface. This could lead to unintended behavior if an invalid address is provided.
- Impact: Setting an invalid `feeRedistributor` address could cause the contract to malfunction or become unusable.

### Potential Division by Zero in `getFees`
- Location: `contracts/Curves.sol` : `getFees`
- Mechanism: Although the division in `getFees` is by a constant (`1 ether`), it's essential to ensure that the `feesEconomics.protocolFeePercent`, `feesEconomics.subjectFeePercent`, `feesEconomics.referralFeePercent`, and `feesEconomics.holdersFeePercent` are not set to values that cause the fees to exceed the maximum allowed value when divided, potentially leading to overflow or underflow. However, the primary concern here would be ensuring these percentages are valid and correctly set.
- Impact: Incorrectly set fee percentages could lead to miscalculated fees, potentially causing financial losses or unintended behavior in the contract.

### Unauthorized Access in `setReferralFeeDestination`
- Location: `contracts/Curves.sol` : `setReferralFeeDestination`
- Mechanism: The `setReferralFeeDestination` function allows the `curvesTokenSubject` to set the referral fee destination without checking if the caller is authorized to do so for the specified `curvesTokenSubject`. However, it does use the `onlyTokenSubject(curvesTokenSubject)` modifier, which restricts the function to only be callable by the `curvesTokenSubject` itself, mitigating the risk.
- Impact: Given the use of `onlyTokenSubject(curvesTokenSubject)`, the risk is mitigated, but ensuring proper authorization and access control is crucial.

### Missing Zero-Address Check in `CurvesERC20Factory.deploy`
- Location: `contracts/CurvesERC20Factory.sol` : `deploy`
- Mechanism: The `deploy` function in `CurvesERC20Factory` does not check if the `owner` parameter is a zero address before deploying a new `CurvesERC20` contract. Deploying a contract with a zero address as the owner could lead to issues with the contract's functionality, as the `Ownable` contract from OpenZeppelin expects a valid owner address.
- Impact: Deploying a contract with a zero address as the owner could render the contract unusable due to the `Ownable` contract's access control mechanisms. 

### Potential Reentrancy in `FeeSplitter.claimFees` and `FeeSplitter.batchClaiming`
- Location: `contracts/FeeSplitter.sol` : `claimFees` and `batchClaiming`
- Mechanism: Both `claimFees` and `batchClaiming` functions in `FeeSplitter` transfer funds to the user after updating the contract's state. This pattern is vulnerable to reentrancy attacks if the recipient is a contract that can reenter the `FeeSplitter` contract.
- Impact: An attacker could potentially drain the contract by reentering it and claiming fees multiple times before the contract state is updated to reflect the claimed fees.
