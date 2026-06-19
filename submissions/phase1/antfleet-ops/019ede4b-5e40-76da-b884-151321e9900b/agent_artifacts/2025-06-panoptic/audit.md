# Audit: 2025-06-panoptic

## Ignoring Negative Pool Exposure Leads to NAV Overstatement and Vault Drain
- Location: `src/accountants/PanopticVaultAccountant.sol` : `computeNAV`
- Mechanism: When calculating the net asset value (NAV) of the vault, the accountant sums the exposures of each pool and explicitly clamps negative values to zero using `Math.max(poolExposure0 + poolExposure1, 0)`. This means if a vault's position in a Panoptic pool is underwater (has a negative mark-to-market value or debt), the loss is completely ignored in the NAV calculation.
- Impact: The vault's reported NAV will be artificially inflated whenever positions are losing money. Malicious users or the manager can withdraw their shares at the inflated NAV, draining the vault of real underlying assets. The remaining users will be left holding the bag for the unrealized losses, potentially rendering the vault deeply insolvent.

## Value Leakage to Withdrawing Users Due to Delayed TotalSupply Update
- Location: `src/HypoVault.sol` : `requestWithdrawal` / `fulfillDeposits`
- Mechanism: When a user requests a withdrawal, their shares are "virtually burned" (removed from their `balanceOf`), but the global `totalSupply` is not decreased until the manager later calls `fulfillWithdrawals`. During the asynchronous window between the withdrawal request and its fulfillment, `totalSupply` remains artificially inflated. When `fulfillDeposits` is called during this window, the share price is calculated using this inflated `totalSupply`, causing new depositors to receive fewer shares than they mathematically should.
- Impact: This creates a "withdrawal overhang" that systematically leaks value from new depositors to existing shareholders. New depositors effectively subsidize the withdrawing users because the pending withdrawal shares still count towards the total supply used to price the new deposits. Over time, or with large withdrawal requests, this results in measurable financial loss for incoming liquidity.
