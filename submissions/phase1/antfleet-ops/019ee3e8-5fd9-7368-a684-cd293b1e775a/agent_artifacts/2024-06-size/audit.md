# Audit: 2024-06-size

# Reentrancy vulnerability in `liquidate` and `liquidateWithReplacement` functions

## Location: 
- `liquidate` function: `src/Size.sol` : `liquidate(LiquidateParams calldata params)`
- `liquidateWithReplacement` function: `src/Size.sol` : `liquidateWithReplacement(LiquidateWithReplacementParams calldata params)`

## Mechanism: 
The `liquidate` and `liquidateWithReplacement` functions are vulnerable to reentrancy attacks. 
In the `liquidate` function, after the protocol takes the collateral from the borrower and transfers it to the liquidator, it calls `executeLiquidate` which then calls `state.data.borrowAToken.transferFrom(msg.sender, address(this), debtPosition.futureValue);`. 
Similarly, in the `liquidateWithReplacement` function, it calls `executeLiquidateWithReplacement` which then calls `state.data.borrowAToken.transferFrom(address(this), params.borrower, issuanceValue);` and `state.data.borrowAToken.transferFrom(address(this), state.feeConfig.feeRecipient, liquidatorProfitBorrowToken);`. 
If the `borrowAToken` contract is a malicious contract, it could reenter the `liquidate` or `liquidateWithReplacement` function, potentially draining the protocol's funds.

## Impact: 
An attacker could exploit this vulnerability to drain the protocol's funds, potentially leading to significant financial losses.

To fix this vulnerability, the `liquidate` and `liquidateWithReplacement` functions should be modified to use the Checks-Effects-Interactions pattern, where all checks are performed before any effects (state changes) are made, and interactions with other contracts are performed last. 

Here is a possible fix:
```solidity
function liquidate(LiquidateParams calldata params)
    external
    payable
    override(ISize)
    whenNotPaused
    returns (uint256 liquidatorProfitCollateralToken)
{
    //... (rest of the function remains the same)

    // Calculate the profit
    uint256 assignedCollateral = state.getDebtPositionAssignedCollateral(debtPosition);
    uint256 debtInCollateralToken = state.debtTokenAmountToCollateralTokenAmount(debtPosition.futureValue);
    uint256 protocolProfitCollateralToken = 0;

    //... (rest of the function remains the same)

    // Transfer the collateral to the liquidator
    state.data.collateralToken.transferFrom(debtPosition.borrower, msg.sender, liquidatorProfitCollateralToken);
    state.data.collateralToken.transferFrom(debtPosition.borrower, state.feeConfig.feeRecipient, protocolProfitCollateralToken);

    // Transfer the borrow tokens to the protocol
    state.data.borrowAToken.transferFrom(msg.sender, address(this), debtPosition.futureValue);

    //... (rest of the function remains the same)
}

function liquidateWithReplacement(LiquidateWithReplacementParams calldata params)
    external
    payable
    override(ISize)
    whenNotPaused
    onlyRole(KEEPER_ROLE)
    returns (uint256 liquidatorProfitCollateralToken, uint256 liquidatorProfitBorrowToken)
{
    //... (rest of the function remains the same)

    // Calculate the profit
    uint256 assignedCollateral = state.getDebtPositionAssignedCollateral(debtPosition);
    uint256 debtInCollateralToken = state.debtTokenAmountToCollateralTokenAmount(debtPosition.futureValue);
    uint256 protocolProfitCollateralToken = 0;

    //... (rest of the function remains the same)

    // Transfer the collateral to the liquidator
    state.data.collateralToken.transferFrom(debtPosition.borrower, msg.sender, liquidatorProfitCollateralToken);
    state.data.collateralToken.transferFrom(debtPosition.borrower, state.feeConfig.feeRecipient, protocolProfitCollateralToken);

    // Transfer the borrow tokens to the protocol
    state.data.borrowAToken.transferFrom(address(this), params.borrower, issuanceValue);
    state.data.borrowAToken.transferFrom(address(this), state.feeConfig.feeRecipient, liquidatorProfitBorrowToken);

    //... (rest of the function remains the same)
}
```
In the fixed version, the collateral is transferred to the liquidator before the borrow tokens are transferred to the protocol, preventing a potential reentrancy attack.
