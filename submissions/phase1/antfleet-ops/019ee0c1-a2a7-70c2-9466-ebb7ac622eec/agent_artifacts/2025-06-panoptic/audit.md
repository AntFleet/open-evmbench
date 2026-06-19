# Audit: 2025-06-panoptic

## Token1 premium sign is reversed in NAV

- Location: `src/accountants/PanopticVaultAccountant.sol` : `computeNAV`
- Mechanism: `poolExposure0` correctly values premiums as `shortPremium.rightSlot() - longPremium.rightSlot()`, but `poolExposure1` uses the opposite sign: `longPremium.leftSlot() - shortPremium.leftSlot()`. Short premiums owed to the vault are assets and long premiums are liabilities, so token1 exposure should be calculated the same way as token0. This makes the accountant understate NAV when token1 short premiums exceed long premiums, and overstate NAV when token1 long premiums exceed short premiums.
- Impact: Deposits and withdrawals are priced against an incorrect NAV in `fulfillDeposits` and `fulfillWithdrawals`. Users can receive too many or too few shares/assets depending on the sign of token1 premium imbalance, allowing value transfer between entering, exiting, and remaining vault users.

## Underlying cash is inconsistently netted against negative pool exposure

- Location: `src/accountants/PanopticVaultAccountant.sol` : `computeNAV`
- Mechanism: The accountant applies `Math.max(poolExposure0 + poolExposure1, 0)` inside the per-pool loop. If the vault’s underlying token is one of a pool’s `token0`/`token1`, the vault’s underlying balance is added into that pool exposure before the per-pool floor. If the underlying token is not in any configured pool, the same underlying balance is added only after the loop. Economically equivalent vault states can therefore produce different NAVs depending only on whether the underlying token appears in the pool list.
- Impact: NAV can be under- or over-reported. A user can deposit when NAV is understated to mint excess shares, or withdraw when NAV is overstated to receive excess underlying, diluting or draining value from other vault users.

