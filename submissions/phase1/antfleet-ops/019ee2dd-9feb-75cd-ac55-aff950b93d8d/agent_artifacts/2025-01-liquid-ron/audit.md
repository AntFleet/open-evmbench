# Audit: 2025-01-liquid-ron

 Here are the genuine security vulnerabilities found in the codebase.

## 1. Broken `onlyOperator` access-control modifier
- **Location:** `src/LiquidRon.sol` : `modifier onlyOperator()`
- **Mechanism:** The condition is `if (msg.sender != owner() || operator[msg.sender]) revert ErrInvalidOperator();`. Because it uses `||`, any caller that is not the owner reverts regardless of the `operator` flag, and if the owner is also flagged as an operator the call also reverts. The intended logic would allow either the owner or an address with `operator[addr] == true`.
- **Impact:** The operator role is effectively disabled; only the raw owner can call `harvest`, `delegateAmount`, `redelegateAmount`, `undelegateAmount`, `finaliseRonRewardsForEpoch`, etc. If the owner ever accidentally sets `operator[owner] = true`, all operator-gated functions revert until it is unset, breaking staking operations and epoch finalisation.

## 2. ERC4626 share-price inflation / first-depositor attack
- **Location:** `src/LiquidRon.sol` : `totalAssets()` and the inherited ERC4626 `deposit`/`mint`/`withdraw`/`redeem` conversions
- **Mechanism:** `totalAssets()` equals `super.totalAssets() + getTotalStaked() + getTotalRewards()`, where `super.totalAssets()` is simply the vault’s WRON balance. The contract does not override `_decimalsOffset()` (so it defaults to `0`) and has no minimum deposit. An attacker can mint a single share (e.g. deposit 1 wei) and then directly donate a large amount of WRON to the vault. The donated WRON inflates `totalAssets()` while `totalSupply` stays tiny, so the next depositor receives `assets * totalSupply / totalAssets` shares, which rounds down to 0 for deposits up to the donation size.
- **Impact:** Later depositors can be robbed of their principal. The attacker redeems their small share balance for the entire pool, including the victims’ deposits.

## 3. Owner can instantly manipulate conversions via `operatorFee`
- **Location:** `src/LiquidRon.sol` : `setOperatorFee()`, `getTotalRewards()`, `totalAssets()`
- **Mechanism:** `setOperatorFee` is protected only by `onlyOwner` and has no timelock. `totalAssets()` calls `getTotalRewards()`, which immediately applies the current `operatorFee` to all unharvested rewards. Changing the fee therefore changes `totalAssets()` and every share/asset conversion preview in the same block.
- **Impact:** A malicious or compromised owner can front-run a user’s `withdraw`/`redeem` or a `finaliseRonRewardsForEpoch` by raising the fee, causing the transaction to compute fewer assets for the same number of shares, then lower the fee again afterwards. This extracts value from depositors and distorts the withdrawal-epoch price.

## 4. Accrued operator fees are not reserved from `totalAssets`
- **Location:** `src/LiquidRon.sol` : `harvest()`, `harvestAndDelegateRewards()`, `totalAssets()`, `fetchOperatorFee()`
- **Mechanism:** Both harvest functions add `(harvestedAmount * operatorFee) / BIPS` to `operatorFeeAmount`, but `totalAssets()` never subtracts this liability. After a harvest, `super.totalAssets()` includes the full gross rewards while `operatorFeeAmount` records the owed fee; the fee is only removed from the vault when `fetchOperatorFee` is called.
- **Impact:** The net asset value per share is overstated between harvest and fee withdrawal. The fee recipient can time `fetchOperatorFee` to drop the share price immediately before other users redeem, transferring value to themselves. In addition, `harvestAndDelegateRewards` accrues fees without any assets entering the vault, so `operatorFeeAmount` can exceed liquid WRON and cause `fetchOperatorFee` to revert.

## 5. `pruneValidatorList` reads validator rewards with reversed arguments
- **Location:** `src/LiquidRon.sol` : `pruneValidatorList()`
- **Mechanism:** The rest of the codebase uses `getRewards(user, consensusAddrs)` with `user` set to the staking proxy. In `pruneValidatorList`, the call is `getReward(vali, proxies[j])`, passing the validator consensus address first and the proxy address second — reversing the expected user/consensus order.
- **Impact:** Rewards for each validator-proxy pair are read incorrectly (typically as zero). Validators that still have claimable rewards can therefore be pruned from the `validators` array. Since `getTotalStaked`, `getTotalRewards`, and `totalAssets()` all iterate over this list, the protocol can undercount its real assets, distorting share price and withdrawal/finalisation payouts. The function is public, so any address can trigger this incorrect state.

## 6. Epoch redemption underpays requesters and locks residual WRON in escrow
- **Location:** `src/LiquidRon.sol` : `redeem(uint256 _epoch)` and `_convertToAssets()`
- **Mechanism:** `redeem(uint256 _epoch)` uses `_convertToAssets(shares, assetSupply, shareSupply) = shares * (assetSupply + 1) / (shareSupply + 10 ** _decimalsOffset())` with `Math.Rounding.Floor`. `_decimalsOffset()` is not overridden, so the denominator is `shareSupply + 1`, not `shareSupply`. When a user redeems their full request, the result is strictly less than the proportional escrowed assets unless `assetSupply == shareSupply`.
- **Impact:** Withdrawal requesters receive less than their pro-rata share of the assets that were moved to escrow during finalisation. The residual WRON remains in the `Escrow` contract with no sweep function, causing a permanent loss of value. The effect is especially severe for small locked-share requests, where the residual can be a large fraction of the escrowed assets.

## 7. Raw ERC20 transfers without return-value checks
- **Location:** `src/RonHelper.sol` : `_depositRONTo()`; `src/LiquidRon.sol` : `redeem(uint256 _epoch)`
- **Mechanism:** `_depositRONTo` calls `IWRON(wron).transfer(to, amount)` through an interface that ignores the return value. `redeem(uint256 _epoch)` calls `IERC20(asset()).transferFrom(escrow, address(this), assets)` without checking the boolean return. Neither uses `SafeERC20`.
- **Impact:** If the WRON/asset token returns `false` on failure instead of reverting, the contract proceeds as if the transfer succeeded. In `_depositRONTo` the vault may record a harvest/undelegation that never reached the vault; in `redeem(uint256)` a withdrawal request can be marked `fulfilled` while the escrowed WRON is never moved, resulting in loss of funds.
