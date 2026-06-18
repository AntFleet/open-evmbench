# Audit: 2025-01-liquid-ron

## Access control logic flaw in `onlyOperator` modifier

- **Location:** `src/LiquidRon.sol` : `onlyOperator` modifier (line ~`if (msg.sender != owner() || operator[msg.sender])`)
- **Mechanism:** The modifier uses `if (msg.sender != owner() || operator[msg.sender]) revert`. This reverts if the caller is not the owner **or** if the caller is marked as an operator. Consequently, an address explicitly set as an operator (with `operator[addr] = true`) can *never* call the protected functions, because the first condition `msg.sender != owner()` is true for any non‑owner and causes a revert. The only account that can successfully call these functions is the owner, and even then only if `operator[owner]` is `false`.
- **Impact:** Functions guarded by `onlyOperator` – including `harvest`, `harvestAndDelegateRewards`, `delegateAmount`, `redelegateAmount`, `undelegateAmount`, and `finaliseRonRewardsForEpoch` – are completely inaccessible to intended operators. The protocol’s operational model (where multiple operators manage staking and withdrawals) is broken. Funds can become stuck because the owner may not be able to harvest rewards or finalise withdrawal epochs if the owner is accidentally set as an operator, leading to a denial of service for all users.

## Operator fee can be withdrawn after deposit, diluting shareholders

- **Location:** `src/LiquidRon.sol` : `harvest` and `harvestAndDelegateRewards` (fee accumulation) and `fetchOperatorFee` (fee withdrawal)
- **Mechanism:** When rewards are harvested via `harvest` or `harvestAndDelegateRewards`, the full claimed amount is deposited into the vault (increasing `totalAssets`), and the operator’s fee is only recorded as a separate variable `operatorFeeAmount`. The fee is not deducted from the vault’s assets at the time of harvest. Later, `fetchOperatorFee` transfers the fee from the vault’s balance, reducing `totalAssets`. Because `totalAssets` includes the fee until it is withdrawn, the share price is artificially inflated. A malicious operator can harvest, then observe a new deposit (or deposit themselves), and immediately call `fetchOperatorFee` to extract the fee, causing the depositor’s shares to be worth less than expected.
- **Impact:** The operator can steal value from depositors by front‑running deposits with a fee withdrawal. The fee effectively becomes a “tax” on the vault’s TVL that can be extracted at the expense of late depositors. This violates the expected fee‑on‑harvest model and can lead to systematic loss of user funds.

## Reversed parameters in `pruneValidatorList` allow premature validator removal

- **Location:** `src/LiquidRon.sol` : `pruneValidatorList` (line `IRoninValidator(roninStaking).getReward(vali, proxies[j])`)
- **Mechanism:** The function checks whether a validator has zero rewards and zero staking amounts across all proxies. For the reward check, it calls `getReward(vali, proxies[j])`, but the interface `getReward(address user, address)` expects the *user* (proxy) as the first argument and the validator address as the second. The call reverses the arguments, querying the rewards of the validator as a user from the proxy. This returns 0, leading the function to believe the validator has no rewards. Consequently, a validator that still holds rewards for the proxies may be removed from the `validators` list.
- **Impact:** `totalAssets()` relies on `_getValidators()` to sum staked amounts and rewards. If a validator is incorrectly removed, its staked RON and accrued rewards are excluded from the total assets calculation. The share price becomes lower than the true backing. An attacker can call `pruneValidatorList` (permissionless), force a validator removal, and then redeem shares at an undervalued price, extracting more RON than they are entitled to. This leads to a direct loss of funds for the vault and its users.

## `undelegateAmount` likely fails due to instant wrapping of (possibly) locked RON

- **Location:** `src/LiquidProxy.sol` : `undelegateAmount` (calls `bulkUndelegate` then immediately `_depositRONTo(vault, totalUndelegated)`)
- **Mechanism:** The proxy’s `undelegateAmount` calls `IRoninValidator(roninStaking).bulkUndelegate(...)` and then, in the same transaction, wraps the expected native RON and transfers it to the vault. `bulkUndelegate` likely initiates the undelegation process but does **not** instantly return the undelegated RON (staking contracts typically impose a cooldown period). The proxy’s balance will not yet contain the undelegated RON, so `_depositRONTo`’s `wron.deposit{value: totalUndelegated}()` will revert due to insufficient balance.
- **Impact:** The `undelegateAmount` function in the vault is completely unusable. Operators cannot withdraw staked RON from validators to process user withdrawals, potentially locking funds in the staking contract. This disrupts the vault’s core withdrawal mechanism and may force a permanent loss of access to the staked assets.
