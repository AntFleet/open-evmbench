# Audit: 2023-07-pooltogether

## Unauthorized minting of accrued yield fees to an arbitrary recipient
- Location: vault/src/Vault.sol : `mintYieldFee`
- Mechanism: `mintYieldFee(uint256 _shares, address _recipient)` is declared `external` with no access control — it only calls `_requireVaultCollateralized()` and checks `_shares <= _yieldFeeTotalSupply`. The `_recipient` is a fully caller-controlled parameter, and the function does `_yieldFeeTotalSupply -= _shares; _mint(_recipient, _shares);`. The accrued `_yieldFeeTotalSupply` is incremented inside `liquidate` (`_increaseYieldFeeBalance(...)`) and represents real value earmarked for the owner-configured `_yieldFeeRecipient`; nothing requires `msg.sender == _yieldFeeRecipient` nor `_recipient == _yieldFeeRecipient`. Any external account can therefore call `mintYieldFee(_yieldFeeTotalSupply, attacker)` and mint the entire accrued fee balance as redeemable Vault shares to themselves.
- Impact: An arbitrary attacker steals all accrued yield-fee shares (redeemable for the underlying asset via `redeem`/`withdraw`), permanently denying the legitimate `_yieldFeeRecipient` the protocol's yield fees.

## Malicious winner hook can revert to grief the claimer's batched prize claim
- Location: vault/src/Vault.sol : `_claimPrize` (invoked from `claimPrizes`)
- Mechanism: `setHooks` lets any account register arbitrary `VaultHooks` (implementation contract plus `useBeforeClaimPrize`/`useAfterClaimPrize` flags) for itself with no validation. During `claimPrizes`, the claimer loops over all `_winners` and calls `_claimPrize`, which unconditionally invokes `hooks.implementation.beforeClaimPrize(...)` and/or `afterClaimPrize(...)` for each winner inside the same transaction, with no `try/catch` and no gas cap. A winner can set a hook whose `beforeClaimPrize`/`afterClaimPrize` always reverts (or burns all forwarded gas); when the claimer includes that winner in a batch, the entire `claimPrizes` transaction reverts, so none of the other winners in the batch are claimed and the claimer loses the gas spent.
- Impact: A single malicious winner can repeatedly force-revert the claimer's batched claims, blocking prize distribution for all other winners in each affected batch and wasting the claimer's gas (denial-of-service / griefing).

