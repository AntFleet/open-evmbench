# Audit: 2024-03-abracadabra-money

## Missing Approval on Staking Contract Update
- Location: `src/blast/BlastOnboardingBoot.sol` : `setStaking`
- Mechanism: The `setStaking` function allows the owner to update the `staking` contract address after the `bootstrap` function has been executed (provided `ready` is still false). However, during `bootstrap`, the LP token (`pool`) approval is only granted to the initially deployed staking contract. When `setStaking` updates the `staking` state variable, it fails to call `pool.safeApprove(address(_staking), totalPoolShares)` for the new contract.
- Impact: If the owner uses this function to change the staking contract post-bootstrap, the `claim()` function will permanently revert for all users. The new staking contract will lack the necessary allowance to pull the LP tokens from the `BlastOnboardingBoot` proxy, effectively locking all user claims unless the owner has a separate, unprompted way to approve the new contract.

## Unchecked Negative Oracle Answers in Aggregator
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `latestAnswer`
- Mechanism: The function retrieves prices from `baseOracle` and `quoteOracle` using `latestAnswer()`, which returns an `int256`. The code directly casts this to `uint256` (`uint256(baseOracle.latestAnswer())`) without verifying that the answer is strictly positive. In Solidity 0.8+, casting a negative `int256` to `uint256` does not revert but instead wraps around to a massive number near `type(uint256).max`.
- Impact: If either underlying oracle experiences a data glitch, reports a negative value, or is maliciously manipulated to return a negative answer, the aggregator will compute an astronomically high normalized price. This will result in a severely inflated `latestAnswer()` for the MagicLP pair, which can be exploited to bypass solvency checks, manipulate liquidation thresholds, or drain funds in downstream protocols (like Cauldrons) that rely on this aggregator for pricing.
