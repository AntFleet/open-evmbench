# Audit: 2024-06-size

here is the complete professional smart-contract security audit of the provided Solidity codebase.

---

## 1. Theft of Leftover and Accidental ETH via `address(this).balance` Sweep
- **Location**: `Deposit.sol` : `executeDeposit`
- **Mechanism**: 
In the `executeDeposit` function of `Deposit.sol`, when `msg.value > 0`, the contract calculates the deposit amount using the total contract balance:
```solidity
        if (msg.value > 0) {
            // do not trust msg.value (see `Multicall.sol`)
            amount = address(this).balance;
            state.data.weth.deposit{value: amount}();
            state.data.weth.forceApprove(address(this), amount);
            from = address(this);
        }
```
All external user-facing methods in `Size.sol` (such as `withdraw`, `buyCreditLimit`, `sellCreditLimit`, etc.) are marked as `payable`. This permits users to accidentally send Ether along with non-deposit transactions. Furthermore, contracts can have Ether forcibly sent to them via `selfdestruct`. 

Because `amount` is set to `address(this).balance`, any Ether locked or accidentally sent to the contract becomes part of the contract's balance. Any subsequent caller can initiate a `deposit` with `msg.value = 1 wei`. This sets `amount` to the contract's entire Ether balance, wrapping all accumulated ETH into `WETH` and minting `collateralToken` (backed 1:1 by WETH) directly to themselves.

- **Impact**: 
An attacker can steal all leftover, accidentally transferred, or forcibly sent Ether in the contract by calling `deposit` with 1 wei of ETH, gaining a corresponding collateral credit within the protocol at no cost.

---

## 2. Token Price and Decimals Mismatch in Liquidation Reward Calculation
- **Location**: `Liquidate.sol` : `executeLiquidate`
- **Mechanism**: 
The `executeLiquidate` function calculates the `liquidatorReward` using `Math.min` on values of two different token denominations and decimals:
```solidity
            uint256 liquidatorReward = Math.min(
                assignedCollateral - debtInCollateralToken,
                Math.mulDivUp(debtPosition.futureValue, state.feeConfig.liquidationRewardPercent, PERCENT)
            );
```
Where:
1. `assignedCollateral - debtInCollateralToken` is formatted in the decimals of the **collateral token** (e.g., `WETH` with 18 decimals).
2. `Math.mulDivUp(debtPosition.futureValue, state.feeConfig.liquidationRewardPercent, PERCENT)` is calculated in the decimals of the **borrow/debt token** (e.g., `USDC` with 6 decimals), since `debtPosition.futureValue` represents the borrow token amount.

These quantities are compared directly and the result `liquidatorReward` is added to `debtInCollateralToken` (which is in collateral tokens) to produce `liquidatorProfitCollateralToken`:
```solidity
            liquidatorProfitCollateralToken = debtInCollateralToken + liquidatorReward;
```

This introduces two distinct, critical vulnerabilities:
* **Decimals Mismatch (e.g., USDC borrow vs WETH collateral)**: The USDC value is priced in 6 decimals, while WETH is in 18 decimals. The USDC-denominated reward value (e.g., `$100` = `100,000,000` USDC) will numerically be much smaller than the WETH-denominated remainder (`1 WETH` = `10^18`). The `Math.min` operation will mistakenly award the liquidator a minuscule reward (e.g., `100,000,000` wei of WETH, worth virtually `$0`), rendering liquidations highly unprofitable.
* **Token Price Mismatch (e.g., DAI borrow vs WETH collateral)**: Even if both tokens have 18 decimals, unit prices are ignored. If WETH = `$3000` and DAI = `$1`, the literal numerical values from the reward percentage are compared directly against the literal numerical values of the collateral, allowing liquidators in certain market conditions to claim an excessive amount of collateral, draining the borrower's excess premium.

- **Impact**: 
For standard loan pairs (e.g., USDC borrow and WETH collateral), liquidations will be unprofitable, causing liquidators to ignore underwater loans and leading to an accumulation of bad debt. For other configurations, borrowers can be inappropriately drained of their excess collateral.
