# Audit: 2023-07-pooltogether

## Unprotected yield fee minting allows theft of all accrued fees
- Location: `Vault.sol` : `mintYieldFee`
- Mechanism: The `mintYieldFee` function is external and has no access control. It directly reduces `_yieldFeeTotalSupply` and mints the requested shares to the caller‑provided `_recipient`. The yield fee is intended to be collected by the `_yieldFeeRecipient` set by the owner, but this restriction is never enforced in the code.
- Impact: Any attacker can call `mintYieldFee` with the full `_yieldFeeTotalSupply` and their own address as recipient, stealing all yield fees that have been accrued. The protocol loses its entire fee revenue.

## Collateralization check excludes unclaimed yield fee shares, enabling under‑collateralization and asset theft
- Location: `Vault.sol` : `_isVaultCollateralized` → `_currentExchangeRate`
- Mechanism: `_isVaultCollateralized` calls `_currentExchangeRate`, which computes the exchange rate using only the minted `_totalSupply` (excluding `_yieldFeeTotalSupply`). The unclaimed yield fee shares represent a liability that is not considered when determining if the vault is collateralized. If the yield vault suffers a loss after fees have been allocated but before they are minted, the vault can appear collateralized while the fee shares are actually unbacked. An attacker can then call `mintYieldFee` (public, no access control) to mint these unbacked shares, causing the vault to become under‑collateralized. The attacker can immediately withdraw the underlying assets, effectively stealing from other depositors.
- Impact: An attacker can drain the vault’s assets by first minting the unbacked yield fee shares and then withdrawing the underlying tokens. Other users bear the loss.

## Division by zero in `liquidate` when yield fee is set to 100%
- Location: `Vault.sol` : `liquidate`
- Mechanism: The fee calculation uses `(FEE_PRECISION - _yieldFeePercentage)` as a denominator. When `_yieldFeePercentage` equals `FEE_PRECISION` (1e9, i.e., 100%), this denominator becomes zero, causing a division by zero revert. The setter `_setYieldFeePercentage` allows the value `FEE_PRECISION` because it only checks `yieldFeePercentage_ > FEE_PRECISION`.
- Impact: If the yield fee is ever set to 100% (by governance mistake or malicious owner), the `liquidate` function will permanently revert, breaking the yield liquidation mechanism and preventing prize token contributions and yield distribution.

## Reentrancy via user‑controlled hooks during prize claims
- Location: `Vault.sol` : `_claimPrize` → `VaultHooks.beforeClaimPrize` / `afterClaimPrize`
- Mechanism: The `claimPrizes` function (callable only by the trusted claimer) invokes user‑supplied hook contracts that can re‑enter the vault. A malicious winner can set hooks that call `mintYieldFee`, `withdraw`, `deposit`, or other state‑changing functions. Although the claimer is trusted, the hooks are not restricted, allowing reentrancy during the claim process.
- Impact: If combined with the unprotected `mintYieldFee`, the hook can steal yield fees. Even if `mintYieldFee` is fixed, reentrancy can be used to manipulate balances or state during prize claims, potentially causing accounting errors or denial of service for the claimer.
