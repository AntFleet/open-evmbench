# Audit: 2025-01-liquid-ron

An audit of the provided smart-contract codebase has been conducted. Below is the report detailing the discovered security vulnerabilities:

## 1. Incorrect `onlyOperator` Modifier Logic Blocks Operators and the Owner
- Location: `LiquidRon.sol` : `onlyOperator`
- Mechanism: The `onlyOperator` modifier contains a flawed Boolean expression:
  ```solidity
  modifier onlyOperator() {
      if (msg.sender != owner() || operator[msg.sender]) revert ErrInvalidOperator();
      _;
  }
  ```
  If a registered operator (who is not the owner) calls a guarded function, `msg.sender != owner()` evaluates to `true`, causing the transaction to revert. If the owner is registered in the `operator` mapping, `operator[msg.sender]` evaluates to `true`, which also triggers a revert.
- Impact: Designated operators can never call core operational functions (such as `harvest`, `delegateAmount`, `undelegateAmount`, `redelegateAmount`, and `finaliseRonRewardsForEpoch`). In addition, the owner will also be permanently locked out if they ever register themselves as an operator.

---

## 2. Accrued Operator Fees Inflate `totalAssets()`, Causing Share Price Manipulation
- Location: `LiquidRon.sol` : `totalAssets()` / `harvest()` / `harvestAndDelegateRewards()`
- Mechanism: The `totalAssets()` function is used to calculate the exchange rate of shares to assets, but it does not subtract the accrued but unwithdrawn operator fees stored in `operatorFeeAmount`. Before a harvest, pending fees are correctly subtracted within `getTotalRewards()`. However, once `harvest()` is executed, the entire claimed reward amount is deposited into the vault's assets (`super.totalAssets()`), while `operatorFeeAmount` increases. Because the fee is not subtracted from `totalAssets()`, the vault's calculated assets (and thus the share price) immediately jump by the fee amount. When `fetchOperatorFee()` is later called to withdraw the fees, the total assets and share price instantly drop.
- Impact: This accounting discrepancy creates an arbitrage opportunity after every harvest. Users can front-run `fetchOperatorFee()` to withdraw at an artificially inflated share price, stealing value from the contract. Alternatively, when the operator withdraws their fees, existing shareholders suffer an unfair, instant loss in share value.

---

## 3. Immediate Deposit in `undelegateAmount` Will Always Revert Due to Undelegation Cooldown
- Location: `LiquidProxy.sol` : `undelegateAmount`
- Mechanism: On the Ronin Network, undelegating RON from a validator does not return the native RON instantly; there is a cooldown lockup period (typically 3 days) before the funds can be claimed. However, in `LiquidProxy.sol`, `undelegateAmount` invokes `bulkUndelegate` and immediately tries to wrap and transfer the undelegated native RON back to the vault using `_depositRONTo(vault, totalUndelegated)`. Because the native RON is not yet present in the proxy's balance, the `IWRON(wron).deposit{value: totalUndelegated}` call will fail.
- Impact: Any attempt to undelegate staked funds will always revert, permanently preventing the vault from retrieving staked assets from validators.

---

## 4. Redundant $O(N^2)$ Loops in `LiquidProxy.sol` `harvest` Can Cause Out-Of-Gas DoS
- Location: `LiquidProxy.sol` : `harvest`
- Mechanism: The `harvest` function iterates over the `_consensusAddrs` array and inside the loop calls `claimRewards` with the *entire* `_consensusAddrs` array:
  ```solidity
  for (uint256 i = 0; i < _consensusAddrs.length; i++) {
      IRoninValidator(roninStaking).claimRewards(_consensusAddrs);
  }
  ```
  If $N$ consensus addresses are provided, the proxy executes $N$ external calls to `claimRewards`, passing an array of size $N$ each time.
- Impact: This behavior is extremely gas-inefficient ($O(N^2)$ complexity) and can easily exceed the block gas limit, causing a Denal-of-Service (DoS) on harvesting. Furthermore, if the Ronin Validator contract reverts when trying to claim rewards that have already been claimed in the same transaction block, the harvest function will be completely bricked.

---

## 5. Wrong Epoch Logged in `redeem` Event
- Location: `LiquidRon.sol` : `redeem`
- Mechanism: In the `redeem(uint256 _epoch)` function, the user specifies the finalized epoch `_epoch` they wish to claim. However, the function records the current, active `withdrawalEpoch` into a local variable `epoch` and emits it inside the `WithdrawalClaimed` event instead of `_epoch`:
  ```solidity
  uint256 epoch = withdrawalEpoch;
  ...
  emit WithdrawalClaimed(msg.sender, epoch, shares, assets);
  ```
- Impact: The emitted event logs the incorrect epoch number (the next active epoch instead of the epoch that was actually redeemed). This will break off-chain monitoring, indexing trackers, and frontend interfaces relying on event logs.
