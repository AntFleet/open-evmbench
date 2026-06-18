# Audit: 2026-01-tempo-feeamm

## Findings

### 1. Reentrancy in `executeFeeSwap` allows draining of validatorToken
- **Location**: `FeeAMM.sol` : `executeFeeSwap`
- **Mechanism**: The function calls `IERC20(userToken).transferFrom(msg.sender, address(this), amountIn)` before updating the pool reserves. If `userToken` is a malicious ERC20 that re‑enters the contract during its `transferFrom`, an attacker can call `executeFeeSwap` again in the same transaction. The re‑entered call sees the original, unchanged reserves, passes the `require` check, and executes another swap. The subsequent reserve updates in the original call will then underflow `reserveValidatorToken` (unchecked arithmetic in Solidity <0.8.0) and transfer the validatorToken to the attacker, draining the pool.
- **Impact**: An attacker can steal all validatorToken from any pool by using a malicious `userToken` to trigger reentrancy.

### 2. Reentrancy in `mint` allows LP token inflation and theft
- **Location**: `FeeAMM.sol` : `mint`
- **Mechanism**: `IERC20(validatorToken).transferFrom(msg.sender, address(this), amountValidatorToken)` is executed before `pool.reserveValidatorToken` is increased. A malicious `validatorToken` can re‑enter `mint` (or any other function) during the transfer. The re‑entered mint calculates liquidity using the old reserves, mints LP tokens, and then the outer mint does the same, effectively minting extra LP tokens without a corresponding deposit of real tokens. The attacker can later burn these inflated LP tokens to extract the pool’s underlying assets.
- **Impact**: An attacker can mint LP tokens that are unbacked and then drain the pool by burning them.

### 3. Reentrancy in `burn` allows double‑spending of LP tokens
- **Location**: `FeeAMM.sol` : `burn`
- **Mechanism**: The function sends `userToken` and `validatorToken` to the caller **before** decreasing `liquidityBalances[poolId][msg.sender]` and the pool reserves. If either token is malicious and triggers a re‑entrant call, the attacker can invoke `burn` again with the same `liquidity` amount. The second call succeeds because the LP balance has not yet been reduced, resulting in the same LP tokens being burned multiple times and the underlying tokens being sent repeatedly.
- **Impact**: An attacker can drain the pool’s entire token reserves by burning a single LP position multiple times.

### 4. Unchecked `uint128` overflow in `executeFeeSwap` corrupts pool reserves
- **Location**: `FeeAMM.sol` : `executeFeeSwap`
- **Mechanism**: `pool.reserveUserToken += uint128(amountIn);` can overflow the `uint128` type because only `amountIn` itself is checked to be ≤ `type(uint128).max` (via `_requireU128`), but the sum `reserveUserToken + amountIn` is not checked. In Solidity <0.8.0, overflow wraps silently. An attacker can call `executeFeeSwap` repeatedly to push `reserveUserToken` toward `2^128 - 1` and then overflow it to a near‑zero value, while the contract’s actual userToken balance remains large.
- **Impact**: The pool’s accounting becomes inconsistent with its real balances, enabling further manipulation and theft via other functions (e.g., `rebalanceSwap` or `burn`).

### 5. Unchecked `uint128` overflow in `mint` corrupts pool reserves
- **Location**: `FeeAMM.sol` : `mint`
- **Mechanism**: `pool.reserveValidatorToken += uint128(amountValidatorToken);` is similarly vulnerable to `uint128` overflow. The mint function only checks that `amountValidatorToken` fits in `uint128`, not the sum. An attacker can mint a huge amount of liquidity, causing `reserveValidatorToken` to wrap around and break the pool’s accounting.
- **Impact**: The pool’s reserves no longer match the actual token balances, leading to incorrect pricing and potential draining of the pool.

### 6. Inverted fee in `rebalanceSwap` allows draining the userToken reserve
- **Location**: `FeeAMM.sol` : `rebalanceSwap`
- **Mechanism**: The input amount is computed as `amountIn = (amountOut * N) / SCALE + 1` where `N = 9985` and `SCALE = 10000`. Since `N < SCALE`, `amountIn` is **smaller** than `amountOut` (e.g., paying 999 validatorToken to receive 1000 userToken). The pool subsidises every swap, losing value on each trade. No invariant prevents repeated calls.
- **Impact**: An attacker can drain the entire `userToken` reserve of any pool with a positive userToken balance, profiting from the pool’s loss. The attack can be executed immediately after some userToken enters the pool (e.g., via `executeFeeSwap`).
