# Audit: 2025-02-thorwallet

# Audit Findings

## Integer Underflow in `withdrawRemainingTitn`
- **Location**: `contracts/MergeTgt.sol` : `withdrawRemainingTitn`
- **Mechanism**: The line `uint256 unclaimedTitn = remainingTitnAfter1Year - initialTotalClaimable;` performs unchecked `uint256` subtraction. `remainingTitnAfter1Year` is captured from `titn.balanceOf(address(this))` at the time of the first call, while `initialTotalClaimable` is captured from `total
