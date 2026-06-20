# Audit: 2024-05-loop

Based on a comprehensive security audit of the `PrelaunchPoints` contract, several direct logic and accounting vulnerabilities have been identified. 

---

## 1. Permanent Locking of ETH/WETH Claims if no ETH is Deposited
- **Location**: `PrelaunchPoints.sol` : `convertAllETH` & `_claim`
- **Mechanism**: The loop protocol allows both native ETH and allowed LRTs/LSTs to be locked. When the owner calls `convertAllETH()`, the contract deposits all of its native ETH into the `lpETH` contract to initiate claims, which sets `startClaimDate` to the current block timestamp and freezes ETH/WETH withdrawals. However, if the protocol receives only LRT deposits (and zero native ETH or WETH deposits), the contract's native ETH balance (`address(this).balance`) at the time of conversion will be `0`. This results in `totalLpETH` being recorded as `0`. 
- **Impact**: Any user who subsequently locks or has previously locked WETH or native ETH will have their `userStake` recorded under the `ETH` key. When they try to claim their `lpETH`, the calculation `claimedAmount = userStake.mulDiv(totalLpETH, totalSupply)` will resolve to `0` (since `totalLpETH` is `0`), resulting in the user receiving `0` `lpETH` and permanently losing their deposited assets.

---

## 2. Inability to Withdraw WETH/ETH in Emergency Mode After `startClaimDate`
- **Location**: `PrelaunchPoints.sol` : `withdraw`
- **Mechanism**: The contract contains an emergency mechanism (`emergencyMode`) intended to bypass all date restrictions to allow users to rescue their locked funds via `withdraw()`. However, inside the `withdraw` function, there is an explicit inner check for the native `ETH` case:
  ```solidity
  if (_token == ETH) {
      if (block.timestamp >= startClaimDate){
          revert UseClaimInstead();
      }
      totalSupply = totalSupply - lockedAmount;
      // ...
  }
  ```
- **Impact**: If an emergency occurs *after* `convertAllETH()` has been called (which sets `startClaimDate = uint32(block.timestamp)`), users who locked native ETH or WETH will not be able to rescue their funds using the `withdraw` function since the transaction will unconditionally revert with `UseClaimInstead()`.

---

## 3. Potential Theft/Inflation of LRT Claims via Pre-existing Native ETH
- **Location**: `PrelaunchPoints.sol` : `_claim` (LRT branch)
- **Mechanism**: When a user claims an LRT token, the contract swaps the designated percentage of their stake to native ETH via 0x API and then wraps it into `lpETH`:
  ```solidity
  _fillQuote(IERC20(_token), userClaim, _data);
  claimedAmount = address(this).balance;
  lpETH.deposit{value: claimedAmount}(_receiver);
  ```
  Instead of utilizing the precise change in balance (`boughtETHAmount` returned by `_fillQuote`), the contract designates `address(this).balance` as the claim amount. 
- **Impact**: If any native ETH is sent directly to the contract (either accidentally, maliciously, or via `selfdestruct` on some contracts), the very next user claiming an LRT token will sweep all pre-existing ETH in the contract, converting it into excess `lpETH` for themselves at the expense of others.

---

## 4. Missing Slippage Protection on LRT Swaps via `0x` Integration
- **Location**: `PrelaunchPoints.sol` : `_validateData` & `_fillQuote`
- **Mechanism**: When swapping LRTs for ETH, the contract delegates validation of the 0x API payload to `_validateData()`. However, the validation checks only ensure key parameter identities (`inputToken`, `outputToken`, `inputTokenAmount` and `recipient`). There is absolutely no validation enforcing a minimum threshold for the out-of-swap rate or output amount (e.g., checking `minBuyAmount` / `minOutputTokenAmount` against an off-chain oracle price or preset slippage limit).
- **Impact**: A user could generate a highly sub-optimal swap path or call, or a malicious actor could front-run/sandwich the transaction, extracting a massive portion of the swap's value, which drastically minimizes the `lpETH` received by the claimer.
