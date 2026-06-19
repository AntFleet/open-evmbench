# Audit: 2024-05-loop

## Incorrect ETH Accounting in `_claim` Sweeps Entire Contract Balance
- Location: `src/PrelaunchPoints.sol` : `_claim`
- Mechanism: When a user claims a non-ETH token, the contract swaps the token to ETH via `_fillQuote` and then deposits the resulting ETH into the `lpETH` contract. However, the amount deposited is calculated as `claimedAmount = address(this).balance;`, which uses the *entire* ETH balance of the contract rather than just the ETH received from the swap. The `_fillQuote` function correctly calculates the swapped amount (`boughtETHAmount = address(this).balance - boughtETHAmount;`) but fails to return it, leading to this accounting error.
- Impact: Any residual ETH in the contract (from direct transfers via the `receive()` function, dust from previous swaps, or incomplete deposits in `convertAllETH`) will be swept into the `lpETH` deposit for the current user. An attacker can exploit this by sending ETH directly to the contract and then claiming a non-ETH token (or claiming 0% of a token with a dummy swap) to steal the residual ETH. This breaks the protocol's accounting and can drain funds that do not belong to the claimer.

## Emergency Mode Fails to Allow ETH Withdrawals After `startClaimDate`
- Location: `src/PrelaunchPoints.sol` : `withdraw`
- Mechanism: The `withdraw` function is designed to allow users to withdraw their locked assets in case of an emergency. While the initial time-based restrictions are correctly bypassed when `emergencyMode` is true, there is a secondary check inside the `if (_token == ETH)` block: `if (block.timestamp >= startClaimDate) { revert UseClaimInstead(); }`. This check is *not* gated by the `!emergencyMode` condition. 
- Impact: If an emergency occurs after `startClaimDate` has passed (e.g., the `lpETH` contract is compromised or paused, making `claim` fail), users will be unable to withdraw their original ETH even with emergency mode enabled. The function will always revert with `UseClaimInstead()`, trapping users' ETH funds during a critical failure scenario.
