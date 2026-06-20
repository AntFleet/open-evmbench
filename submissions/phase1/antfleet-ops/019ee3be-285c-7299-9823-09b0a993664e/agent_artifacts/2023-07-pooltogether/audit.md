# Audit: 2023-07-pooltogether

**mintYieldFee has no access control**

- Location: `Vault.sol` : `mintYieldFee`
- Mechanism: The function is declared `external` with no `onlyOwner`, no check against `_yieldFeeRecipient`, and no other authorization. It simply does `_requireVaultCollateralized()`, subtracts from `_yieldFeeTotalSupply`, and calls `_mint(_recipient, _shares)`.
- Impact: Any caller can mint the entire accrued yield-fee share balance to an arbitrary address (including themselves), stealing all yield fees that were intended for the configured recipient.

**Arbitrary recipient in sponsor path combined with missing TWAB delegation check**

- Location: `Vault.sol` : `_sponsor` (and `sponsor`/`sponsorWithPermit`)
- Mechanism: `_sponsor` calls the normal `deposit` path and then unconditionally calls `_twabController.sponsor(_receiver)` only if the current delegate is not already the sponsorship address. No check prevents a caller from sponsoring on behalf of an arbitrary `_receiver`.
- Impact: An attacker can force sponsorship (and the associated accounting) for any address without that address's consent, potentially affecting prize eligibility or delegation state for victims.

**Reentrancy via user-supplied hooks during prize claiming**

- Location: `Vault.sol` : `_claimPrize` (called from `claimPrizes`)
- Mechanism: `_claimPrize` reads `_hooks[_winner]`, calls the user-supplied `beforeClaimPrize` hook, then `prizePool.claimPrize`, then the `afterClaimPrize` hook. The hooks are completely untrusted contracts chosen by each winner and the calls occur while the prize claim is in progress.
- Impact: A malicious hook implementation can re-enter the Vault (or other contracts) in the middle of a prize claim, potentially causing inconsistent TWAB state, double-claiming, or interference with subsequent claims in the same `claimPrizes` batch.

**Unchecked arithmetic in `_liquidatableBalanceOf` can underflow on refund path**

- Location: `Vault.sol` : `_liquidatableBalanceOf`
- Mechanism: The expression `return _availableYield -= _availableYieldFeeBalance(_availableYield);` is performed inside an `unchecked` block after `availableYieldBalance()` has already returned a non-zero value.
- Impact: If `_availableYieldFeeBalance` ever returns a value larger than `_availableYield` (possible under certain rounding or concurrent state changes), the subtraction silently underflows to a huge number, allowing liquidation of far more shares than the actual liquidatable yield.

**Exchange-rate snapshot used for mint/withdraw can be stale after external yield accrual**

- Location: `Vault.sol` : `_currentExchangeRate`, `_convertToShares`, `_convertToAssets`, `_deposit`, `_withdraw`
- Mechanism: `_lastRecordedExchangeRate` is only updated on `_mint`/`_burn` (i.e., share supply changes). All share <-> asset conversions performed inside the same transaction after a yield-accruing call to the YieldVault read the stale snapshot when `_lastRecordedExchangeRate` is non-zero.
- Impact: An attacker that can force a sequence of `deposit`/`mint` followed immediately by a yield-generating action (or liquidation) can obtain more (or fewer) shares than the true collateral value, enabling share inflation or under-collateralized withdrawals.

**No validation that the supplied YieldVault actually holds the Vault's asset**

- Location: `Vault.sol` : constructor, `_deposit`, `_withdraw`, `_totalAssets`
- Mechanism: The constructor and all accounting functions blindly trust that `_yieldVault.asset() == address(asset())` and that `maxWithdraw`/`deposit`/`withdraw` calls succeed with the expected token. No check or interface call enforces this.
- Impact: Deployment against a mismatched or malicious YieldVault can cause permanent loss of funds, incorrect exchange-rate calculations, or locked assets that can never be withdrawn.
