# Audit: 2025-01-liquid-ron

## Critical Access Control Flaw in `onlyOperator` Modifier
- Location: `src/LiquidRon.sol` : `onlyOperator`
- Mechanism: The modifier uses the logical OR operator incorrectly in its access control check: `if (msg.sender != owner() || operator[msg.sender]) revert ErrInvalidOperator();`. If the caller is an operator but not the owner, `msg.sender != owner()` evaluates to `true`. Due to the `||` operator, the condition short-circuits to `true` and reverts immediately. The only way to pass this modifier is if `msg.sender == owner()` AND `operator[msg.sender] == false`.
- Impact: The `operator` role is completely broken. Addresses granted operator permissions via `updateOperator` will be permanently locked out of all critical management functions (`harvest`, `delegateAmount`, `redelegateAmount`, `undelegateAmount`, `finaliseRonRewardsForEpoch`), forcing the owner to perform all operations and breaking the intended delegated management architecture.

## Accounting Error / Extraction of User Funds in `harvestAndDelegateRewards`
- Location: `src/LiquidRon.sol` : `harvestAndDelegateRewards`
- Mechanism: When this function is called, the `LiquidProxy` delegates 100% of the claimed rewards to a new validator via `delegateRewards`, meaning no WRON is actually sent back to the vault. However, the vault still calculates the operator fee on the full `harvestedAmount` and adds it to `operatorFeeAmount`. 
- Impact: The operator can later call `fetchOperatorFee()` to withdraw this accrued fee from the vault's liquid WRON reserves. Because the underlying rewards were fully reinvested and never entered the vault, the operator is effectively extracting fees from the users' deposited/staked assets, resulting in a direct loss of user funds and share price dilution.

## Denial of Service (DoS) in `LiquidProxy.harvest` via Redundant Loop
- Location: `src/LiquidProxy.sol` : `harvest`
- Mechanism: The function calls `IRoninValidator(roninStaking).claimRewards(_consensusAddrs)` inside a `for` loop that iterates `_consensusAddrs.length` times. The `claimRewards` function already accepts and processes the entire array in a single call. Executing it repeatedly means the second iteration will attempt to claim rewards that were already claimed in the first iteration. If the underlying Ronin staking contract reverts when there are no pending rewards to claim (standard behavior for most staking implementations), the transaction will fail.
- Impact: The `harvest` function will consistently revert whenever the `_consensusAddrs` array contains more than one address. This creates a Denial of Service that prevents the vault from harvesting staking rewards, severely impacting protocol yield.
