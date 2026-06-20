# Audit: 2024-05-arbitrum-foundation

## Unbounded allowance increase to external contract
- Location: src/assertionStakingPool/AssertionStakingPool.sol : createAssertion
- Mechanism: The function unconditionally executes `IERC20(stakeToken).safeIncreaseAllowance(rollup, requiredStake)` (and the analogous call in EdgeStakingPool.createEdge) before the external call to `newStakeOnNewAssertion` (or `createLayerZeroEdge`). If that call reverts (insufficient balance, assertion already made, etc.) the allowance increase has already occurred; repeated calls therefore accumulate an arbitrarily large allowance for the rollup/challenge-manager contract.
- Impact: An attacker who can force repeated reverts (or simply waits until the pool balance grows) can cause the pool to grant the rollup an allowance far larger than any single required stake, enabling the rollup to pull more tokens than the pool ever intended to stake in a single operation.

## Missing validation that stake token is non-zero
- Location: src/assertionStakingPool/AbsBoldStakingPool.sol : constructor
- Mechanism: The immutable `stakeToken` is set directly from the constructor argument with no `address(0)` check; the same pattern appears in AssertionStakingPool and EdgeStakingPool constructors.
- Impact: Deployment with a zero address results in a pool that can never move tokens; all subsequent `safeTransferFrom`/`safeTransfer` calls revert, permanently locking any deposits that reach the contract.

## Reentrancy window after balance update but before external call completion
- Location: src/assertionStakingPool/AbsBoldStakingPool.sol : withdrawFromPool(uint256)
- Mechanism: `depositBalance[msg.sender]` is written before `safeTransfer` is performed; if the ERC-20 implementation (or a hook) re-enters `withdrawFromPool` the reduced balance is already visible, but the original transfer has not yet completed.
- Impact: A malicious token can cause the same user to withdraw the same funds multiple times before the first transfer finishes, resulting in an accounting mismatch between recorded balances and actual token holdings.
