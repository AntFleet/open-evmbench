# Audit: 2024-04-noya

Here is the security audit report for the provided codebase, listing seven genuine high-severity vulnerabilities found in the system.

## 1. Spot Reserves-Based LP Valuation of Camelot and Aerodrome LP Tokens (Oracle Manipulation)
- Location: `CamelotConnector.sol` : `_getPositionTVL`, `AerodromeConnector.sol` : `_getPositionTVL`
- Mechanism: The TVL calculation queries the current spot reserves of the AMM pair and multiplies them by stable oracle prices (`_getValue`). In any AMM obeying constant product invariant $x \cdot y = k$, pushing the pool far off-equilibrium with a large trade always increases the raw nominal sum of reserve values valued at a constant oracle price ($x \cdot P_x + y \cdot P_y$). An attacker can execute a flash loan to trade heavily in one direction, artificially inflating the LP token's TVL momentarily, and then back-run the transaction to restore the pool.
- Impact: An attacker can inflate the recorded TVL right before `calculateDepositShares` or `calculateWithdrawShares` is executed, manipulating the share calculation to either steal assets from the vault during withdrawals or minimize the shares issued to other depositors.

## 2. Registry State Corruption via Incorrect Key Resolution in `updateHoldingPosition`
- Location: `PositionRegistry.sol` : `updateHoldingPosition`
- Mechanism: During the deletion of an active holding position inside the array (the `removePosition` branch), the contract swaps the element being removed with the final element of the `holdingPositions` array. To update the index of the swapped element in the `isPositionUsed` mapping, the code generates the lookup key using `vault.holdingPositions[positionIndex].calculatorConnector` as the first argument. However, when the position is originally inserted, the key is generated using the actual `connector` address (`msg.sender`). This mismatches if `calculatorConnector != connector`.
- Impact: The registry mapping `isPositionUsed` is corrupted and will fail to properly track or update the index of swapped positions. Subsequent attempts to interact with, update, or close these swapped positions will revert, read out-of-bounds, or corrupt other active positions, bricking systemic financial management.

## 3. Inversion of MorphoBlue Debt Liability in TVL Calculation
- Location: `MorphoBlueConnector.sol` : `_getPositionTVL`
- Mechanism: The TVL of a MorphoBlue position is calculated by wrapping both assets and liabilities into a single positive addition: `tvl = _getValue(params.loanToken, base, supplyAmount + borrowAmount + convertCToL(...))`. Here, `borrowAmount` represents the outstanding debt liability, which should be subtracted from the position's net value rather than added.
- Impact: Outstanding debt is treated as an asset rather than a liability, leading to massive artificial inflation of the vault's calculated TVL. Bad actors can take out immense borrow positions to inflate the vault's reported wealth, allowing them to withdraw far more than their share or drain vault funds entirely.

## 4. Unauthenticated Public Reset of Pending Performance Fees
- Location: `AccountingManager.sol` : `checkIfTVLHasDroped`
- Mechanism: The function `checkIfTVLHasDroped()` is a public, unauthenticated function meant to reset pending performance fees if the TVL falls below `storedProfitForFee`. Because anyone can call this function at any time, a griefing actor can wait for minor market changes or intentionally trigger a momentary downward price swing in external integrations, then immediately trigger this function to reset `preformanceFeeSharesWaitingForDistribution` to 0.
- Impact: Malicious actors can indefinitely prevent the strategy managers from collecting their earned performance fees at virtually no cost.

## 5. Clamping of `timePassed` inside `collectManagementFees` Causes Loss of Fee Accrual
- Location: `AccountingManager.sol` : `collectManagementFees`
- Mechanism: If the duration since the last fee distribution exceeds 10 days, the function clamps the calculated accrual period to exactly 10 days (`if (timePassed > 10 days) { timePassed = 10 days; }`). However, after calculating the fee for only 10 days, the contract still sets `lastFeeDistributionTime = block.timestamp`, effectively overriding the unaccounted time.
- Impact: Any accrued management fees accumulated beyond the 10-day period are permanently deleted from history and can never be claimed by the management fee receiver.

## 6. Zero TVL Valuation for Staked Aerodrome LP Positions
- Location: `AerodromeConnector.sol` : `_getPositionTVL`
- Mechanism: The TVL retrieval function for Aerodrome LP positions calculates the quantity of owned LP tokens by querying `IERC20(pool).balanceOf(address(this))`. However, the contract provides a `stake()` function that transfers the LP tokens into the Aerodrome `gauge` contract. Once staked, the balance held locally by the contract becomes `0`, and the staked balance inside the gauge is completely ignored by the TVL function.
- Impact: Staking Aerodrome LP positions instantly zero-outs their calculated TVL. This artificially crashes the vault's reported holdings, allowing users to mint dirt-cheap shares or cause panics.

## 7. Systemic Vault DoS due to Arithmetic Underflow on Insolvent Lending Positions
- Location: `CompoundConnector.sol` : `_getPositionTVL`, `DolomiteConnector.sol` : `_getPositionTVL`, `PrismaConnector.sol` : `_getPositionTVL`, `SiloConnector.sol` : `_getPositionTVL`
- Mechanism: These lending integration contracts compute TVL by subtracting total debt liabilities from total collateral assets (e.g., `totalDepositAmount - totalBAmount` or `totalCollateral - totalDebt`). If a position becomes insolvent or temporarily under-collateralized due to extreme market movements or liquidation, the resulting value is negative. In Solidity 0.8.20, this subtraction will trigger a panic underflow and revert.
- Impact: Because `TVL()` is a critical global dependency for core entrypoints (`deposit`, `withdraw`, `calculateDepositShares`, `calculateWithdrawShares`), a single insolvent position in any of these connectors will cause the entire vault's operations to completely freeze, locking up all user assets indefinitely.
