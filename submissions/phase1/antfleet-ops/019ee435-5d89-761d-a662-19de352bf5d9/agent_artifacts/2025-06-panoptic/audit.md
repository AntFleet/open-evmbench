# Audit: 2025-06-panoptic

No Slither item validated as an in-scope vulnerability. Confirmed findings:

## Token1 premiums are counted with the wrong sign
- Location: `src/accountants/PanopticVaultAccountant.sol` : `computeNAV`
- Mechanism: Token0 premium exposure is computed as `shortPremium - longPremium`, but token1 uses the opposite formula: `longPremium.leftSlot() - shortPremium.leftSlot()`. This reverses whether token1 premium owed to the vault increases NAV or premium owed by the vault decreases NAV.
- Impact: NAV can be materially under- or over-reported whenever positions accrue token1 premiums. Depositors can mint shares too cheaply when NAV is understated, or withdrawers can redeem too much when NAV is overstated, transferring value from other vault users.

## Negative exposure is ignored per pool instead of netted against total vault assets
- Location: `src/accountants/PanopticVaultAccountant.sol` : `computeNAV`
- Mechanism: The accountant adds `max(poolExposure0 + poolExposure1, 0)` to NAV inside each pool loop, then separately adds any uncounted underlying balance. A negative exposure in one pool is floored to zero before it can offset positive exposure or idle assets elsewhere, so liabilities are dropped instead of netted at the portfolio level.
- Impact: Vault NAV is overstated when any pool has net negative exposure while the vault has positive exposure/assets elsewhere. Withdrawers can redeem at an inflated price and drain value from remaining shareholders; new depositors can also be forced to buy overpriced shares.

## Partial deposit rounding desynchronizes queued assets from epoch accounting
- Location: `src/HypoVault.sol` : `fulfillDeposits` / `executeDeposit`
- Mechanism: `fulfillDeposits` carries only the aggregate remainder `assetsDeposited - assetsToFulfill` into the next epoch, but `executeDeposit` floors each user’s fulfilled amount independently and carries each user’s individual remainder forward. With many small deposits, the sum of per-user remainders can exceed the aggregate remainder recorded in `depositEpochState[epoch + 1]`.
- Impact: An attacker can split deposits across many addresses before a partial fulfillment, causing later epochs to process more queued assets than the epoch accounting expects. This can mint excess shares relative to the shares added to `totalSupply`, diluting existing holders and potentially causing later cancellation/execution underflows.

## Partial withdrawal rounding desynchronizes queued shares and reserved assets
- Location: `src/HypoVault.sol` : `fulfillWithdrawals` / `executeWithdrawal`
- Mechanism: `fulfillWithdrawals` carries the aggregate unfulfilled shares into the next epoch, while `executeWithdrawal` floors each user’s fulfilled shares independently and carries per-user remainders. The summed per-user rollover can exceed `withdrawalEpochState[epoch + 1].sharesWithdrawn`; basis is also consumed according to the aggregate fulfillment ratio even when a user’s rounded fulfilled shares are zero.
- Impact: A split withdrawal can make later epochs pay out more shares than were recorded for that epoch, consuming reserved assets that belong to other withdrawers. Users can be underpaid, overcharged performance fees, or left unable to execute/cancel cleanly once the accounting diverges.

