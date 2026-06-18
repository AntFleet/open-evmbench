# Audit: 2024-06-size

## 1. Reentrancy in Deposit and Withdraw Functions

- **Location**:
  - `src/libraries/actions/Deposit.sol` → `executeDeposit` → `depositUnderlyingBorrowTokenToVariablePool`
  - `src/libraries/actions/Withdraw.sol` → `executeWithdraw` → `withdrawUnderlyingTokenFromVariablePool`
- **Mechanism**: The protocol performs external calls to untrusted contracts (underlying token transfers and Aave pool withdrawals) without any reentrancy protection. In `depositUnderlyingBorrowTokenToVariablePool`, `safeTransferFrom` is called on the underlying borrow token, and the internal `borrowAToken` minting happens **after** this external call. If the token offers a callback (e.g., ERC777), an attacker can re-enter the protocol before the mint is recorded. In `withdrawUnderlyingTokenFromVariablePool`, the `borrowAToken` burn occurs before the external `variablePool.withdraw`, but the crucial `validateUserIsNotBelowOpeningLimitBorrowCR` check happens **after** the entire `executeWithdraw` returns, allowing a re-entrant call to manipulate the user’s collateral ratio or borrowAToken balance during the withdrawal.
- **Impact**: An attacker can use a token with a callback (or a malicious contract as the withdrawal recipient) to re-enter the protocol and, for example, borrow funds without proper collateral, double-spend borrowAToken, or bypass the opening-borrow-CR check. This can lead to direct loss of funds from the protocol.

## 2. Incorrect Validation in `updateConfig` for `crLiquidation` Prevents Increasing the Parameter

- **Location**: `src/libraries/actions/UpdateConfig.sol` : `executeUpdateConfig`
- **Mechanism**: When updating the `crLiquidation` key, the logic checks `if (params.value >= state.riskConfig.crLiquidation)` and reverts if true. This means the new value must be **strictly less than** the current value; the administrator can only decrease the liquidation collateral ratio and can never increase it again. The intention was likely to enforce a safety bound (e.g., `params.value > state.riskConfig.crOpening`), but the current condition permanently locks the parameter into a descending direction.
- **Impact**: If the protocol is initialised with a `crLiquidation` that later turns out to be too low (allowing too many liquidations) or if the admin accidentally sets it to an extremely low value, the parameter cannot be corrected upward. This can lead to systemic risk, incorrect liquidations, and loss of user funds.

## 3. Price Feed Missing `answeredInRound` and Min/Max Price Checks

- **Location**: `src/oracle/PriceFeed.sol` : `getPrice` and `_getPrice`
- **Mechanism**: The `PriceFeed` contract uses Chainlink’s `latestRoundData()` but only checks for a non-positive price and a stale timestamp. It does not verify that `answeredInRound >= roundId`, which ensures the data is from the current reporting round. Additionally, it does not check that the returned price falls within the oracle’s predefined `minAnswer`/`maxAnswer` bounds. These omissions can allow the protocol to consume a price that is valid according to timestamp but was not actually updated in the current round, or to accept prices outside the normal range during a flash crash or oracle manipulation.
- **Impact**: An attacker who can delay or manipulate the oracle (e.g., via a flash-loan attack on the underlying feed) can provide a stale or extreme price, leading to incorrect collateral-ratio calculations. This can be exploited to borrow against undervalued collateral, liquidate healthy positions, or avoid liquidation.

## 4. Reentrancy Amplification via `multicall`

- **Location**: `src/Size.sol` : `multicall` → `src/libraries/Multicall.sol` : `multicall`
- **Mechanism**: The `multicall` function uses `functionDelegateCall` to execute an arbitrary sequence of protocol actions. Neither `multicall` itself nor the individual actions (deposit/withdraw) carry a reentrancy guard. Because `multicall` can batch multiple state-changing calls, a reentrancy exploit in a single action (e.g., deposit) can be combined with other actions inside the same multi-call, making it easier to craft a complex attack that manipulates balances and bypasses checks.
- **Impact**: Increases the severity of the reentrancy vulnerability described in finding #1. An attacker can orchestrate a multi-step attack within a single transaction, potentially draining larger amounts or bypassing multiple safety checks that would normally be enforced between separate transactions.
