# Audit: 2025-05-blackhole

## Theft / Permanent Lock of Bribes for Auto-Voting Users
- Location: `Bribes.sol` : `getReward`
- Mechanism: The function checks if `_owner == avm` where `avm` is the `AutoVotingEscrowManager` address. However, when users opt into auto-voting, their locks are transferred to and held by individual child `AutoVotingEscrow` instances rather than the manager contract itself. Consequently, the conditional check `_owner == avm` evaluates to false, and the bribe rewards are transferred directly to the child `AutoVotingEscrow` contract address. Because `AutoVotingEscrow` is not designed to receive, release, or manage arbitrary ERC20 tokens, these rewards are permanently trapped.
- Impact: 100% of the bribe rewards earned by any user locks that opt into auto-voting are permanently locked and lost.

## Permanent Loss of Claimed Rewards in `RewardsDistributor.claim_many`
- Location: `RewardsDistributor.sol` : `claim_many`
- Mechanism: In `claim_many`, when an expired lock is processed, it queries its current owner using standard ERC721 owner lookup and transfers the reward token Directly to that address. For auto-voting locks, this address is the `AutoVotingEscrow` instance. Unlike the single `claim` function, which correctly has a fallback check utilizing `avm.getOriginalOwner(_tokenId)`, `claim_many` lacks this fallback check completely.
- Impact: Claimed reward tokens from expired auto-voting locks are permanently stuck in the non-upgradable `AutoVotingEscrow` contract, resulting in complete loss.

## Concentrated Liquidity Gauge Creation Always Reverts
- Location: `GaugeFactoryCL.sol` : `createEternalFarming`
- Mechanism: `createGauge` handles the creation of a new CL gauge by calling the internal helper `createEternalFarming`. Inside this helper, a call is made to `IAlgebraEternalFarmingCustom.createEternalFarming` with a dummy incentive reward of `1e10` units of `_rewardToken`, which attempts to transfer this amount from the caller (`GaugeFactoryCL`) to the farming contract. Because the factory is a newly deployed contract that holds no balance of `_rewardToken` and lacks a funding mechanism, this transfer will always fail.
- Impact: Concentrated liquidity gauge creation will always revert on-chain, rendering the liquidity mining features of the CL pools broken.

## Slippage Sandwich Attack during `GenesisPool` Launch Leading to Locked Funds
- Location: `GenesisPool.sol` : `_addLiquidityAndDistribute`
- Mechanism: The `addLiquidity` call on the router passes `0` as both `amountAMin` and `amountBMin`. An attacker can manipulate pool reserves in a frontrunning transaction to skew the token ratio. Because there are no slippage controls, the router will execute the deposit at this skewed ratio, consuming only a fraction of the funding token and leaving the remaining excess in the `GenesisPool` contract.
- Impact: Unused tokens are returned and left stuck in the contract. Since the pool status is updated to `LAUNCH` or `PARTIALLY_LAUNCHED`, the owner can no longer request a refund or retrieve them, resulting in permanent lockup of user-contributed capital.

## Broken `MinterUpgradeable.sol` `nudge` Due to Missing Function `status()`
- Location: `MinterUpgradeable.sol` : `nudge`
- Mechanism: `nudge` attempts to read the state of the active governor using `IBlackGovernor(_epochGovernor).status()`. However, `BlackGovernor` is based on OpenZeppelin's standard Governor contract, which exposes `state(uint256)` but does not implement or inherit any external `status()` function.
- Impact: Calling `nudge` will always revert on-chain, rendering the core governance control over tail emission adjustments completely unusable.

## API Helper Exposes Incorrect Claimable Fee Calculations due to `staticcall` State Violation
- Location: `APIHelper/AlgebraPoolAPI.sol` : `getAllPositionsInfo`
- Mechanism: To dynamically fetch current claimable fees, the external helper issues a `staticcall` query to `INonfungiblePositionManager.collect`. However, `collect` is a state-modifying function in Algebra/Uniswap V3 that updates internal fee growth values and transfers tokens. Invoking state-modifying logic within a read-only `staticcall` always triggers a EVM state violation and reverts.
- Impact: The execution of the contract call will silently fail inside the `try-catch` wrapper, causing the external API to incorrectly report `claimableFee0` and `claimableFee1` as `0` for all query positions.

## Bribe Contract `earned()` Gas Exhaustion Denial of Service
- Location: `Bribes.sol` : `earned`
- Mechanism: The calculation iterates over past periods to sum up rewards for each epoch since the user's last claim. Within this loop, the contract queries checkpoints using multiple nested binary searches (`getPriorBalanceIndex` and `getPriorSupplyIndex`). If a user has not claimed for an extended duration, the number of iterations grows.
- Impact: The transaction will exceed the block gas limit and revert, preventing the user from claiming their bribes. Since there is no batch configuration to claim epoch-by-epoch, the funds are permanently locked.
