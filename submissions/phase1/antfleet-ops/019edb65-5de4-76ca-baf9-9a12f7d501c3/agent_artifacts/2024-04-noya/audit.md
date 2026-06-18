# Audit: 2024-04-noya

## 1. OnlyVaultMaintainer modifier logic is wrong, blocking the maintainer role

- Location: `Registry.sol` : `onlyVaultMaintainer` modifier
- Mechanism: The modifier uses `||` instead of `&&`:
  ```solidity
  if (msg.sender != vaults[_vaultId].maintainer || hasRole(EMERGENCY_ROLE, msg.sender) == false)
  ```
  Because of the `||`, even when `msg.sender` is the maintainer, the condition becomes `false || (emergency == false)` which is `true` if the maintainer does not also hold the `EMERGENCY_ROLE`. This causes the modifier to revert for the legitimate maintainer.
- Impact: The maintainer cannot call any function protected by this modifier (`addConnector`, `updateConnectorTrustedTokens`, `removeTrustedPosition`, etc.), effectively breaking the governance of the vault. An attacker who obtains the maintainer role cannot perform their duties; moreover, if the maintainer is the only one who can update connectors, the vault becomes stuck.

## 2. BalancerConnector severely undervalues LP positions

- Location: `BalancerConnector.sol` : `_getPositionTVL`
- Mechanism: The function computes TVL using only a single token from the Balancer pool, ignoring all other tokens:
  ```solidity
  uint256 token1bal = valueOracle.getValue(pool.tokens[pool.tokenIndex], base, _tokenBalances[pool.tokenIndex]);
  return (((1e18 * token1bal * lpBalance) / _weight) / _totalSupply);
  ```
  It does not iterate over the other tokens in the pool, so the value of the LP position is based on one token’s weight and balance, completely missing the contribution of the rest of the pool. This leads to a large understatement of the vault’s total assets.
- Impact: The TVL reported by the vault is wrong, causing the share price to be lower than reality. An attacker can deposit funds when the share price is artificially low (getting more shares) and withdraw when the price corrects, stealing value from the vault. The vault’s profit calculation and fee mechanics are also distorted.

## 3. MorphoBlueConnector adds borrow amount instead of subtracting it, overstating TVL

- Location: `MorphoBlueConnector.sol` : `_getPositionTVL`
- Mechanism: The TVL calculation mixes the borrow amount as if it were an asset:
  ```solidity
  tvl = _getValue(
      params.loanToken,
      base,
      supplyAmount + borrowAmount + convertCToL(pos.collateral, params.oracle, params.collateralToken)
  );
  ```
  The `borrowAmount` is a debt that should be subtracted from the position’s value. Adding it inflates the vault’s total assets, making the share price appear higher than it actually is.
- Impact: The vault’s share price is overvalued. Depositors get fewer shares than they should, and withdrawals receive more underlying than they are entitled to. The vault can be drained by withdrawing at the inflated price, and profit calculations are incorrect.

## 4. SNXConnector ignores debt (minted sUSD), overstating TVL

- Location: `SNXConnector.sol` : `_getPositionTVL`
- Mechanism: The function returns only the collateral value:
  ```solidity
  tvl = _getValue(collateralType, base, totalDeposited + totalAssigned);
  ```
  It does not account for any minted sUSD debt that the position may have. The connector’s `mintOrBurnSUSD` allows borrowing, but the TVL calculation never subtracts that debt.
- Impact: The vault’s total assets are overstated whenever a position has borrowed sUSD. This causes the share price to be too high, enabling attackers to withdraw more than the vault actually holds, leading to loss of funds.

## 5. CurveConnector uses a single-token withdrawal estimate, potentially undervaluing TVL

- Location: `CurveConnector.sol` : `_getPositionTVL` → `LPToUnder`
- Mechanism: The TVL of a Curve LP position is computed by estimating the amount of a single token (chosen by `defaultWithdrawIndex`) that the LP balance can be withdrawn for, and then valuing only that token. The function calls `curvePool.calc_withdraw_one_coin` for that single token, ignoring the other tokens in the pool. If the pool is imbalanced or the chosen token is not the most valuable, the computed value will be lower than the true value of the LP position.
- Impact: The vault’s TVL is understated, leading to an artificially low share price. Depositors can mint shares at a discount, and the vault’s profit and fee calculations are off. Although the manager can choose the `defaultWithdrawIndex`, the calculation is still incorrect because it does not represent the full basket of the LP token.
