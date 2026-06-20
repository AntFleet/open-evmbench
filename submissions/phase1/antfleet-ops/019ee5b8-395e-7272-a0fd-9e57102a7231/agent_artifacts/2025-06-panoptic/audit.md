# Audit: 2025-06-panoptic

## Token1 Premiums Are Counted With The Wrong Sign
- Location: `src/accountants/PanopticVaultAccountant.sol` : `computeNAV`
- Mechanism: `poolExposure0` correctly treats `shortPremium` as an asset and `longPremium` as a liability by computing `shortPremium.rightSlot() - longPremium.rightSlot()`. For token1, the code reverses the sign: `longPremium.leftSlot() - shortPremium.leftSlot()`. This makes token1 premiums owed to the vault reduce NAV, and token1 premiums owed by the vault increase NAV.
- Impact: The vault NAV can be materially over- or under-reported whenever Panoptic positions accrue token1 premiums. Deposits and withdrawals are then fulfilled at the wrong share price, transferring value between depositors, withdrawers, and remaining vault shareholders.

## Underlying Cash Is Netted Inconsistently Against Negative Pool Exposure
- Location: `src/accountants/PanopticVaultAccountant.sol` : `computeNAV`
- Mechanism: The accountant clamps each pool’s exposure with `Math.max(poolExposure0 + poolExposure1, 0)` inside the pool loop. If the underlying token is part of a configured pool, the vault’s underlying balance is added to that pool exposure before the clamp and can be consumed by negative exposure. If the underlying token is not part of any configured pool, the same underlying balance is added only after all per-pool negative exposures have already been floored to zero. Economically equivalent vault states can therefore produce different NAVs depending only on whether the underlying token appears in `pools`.
- Impact: NAV can be overstated when negative pool exposure is ignored before idle underlying is added. Withdrawers can redeem too much underlying at the expense of remaining users, and depositors can receive mispriced shares.

