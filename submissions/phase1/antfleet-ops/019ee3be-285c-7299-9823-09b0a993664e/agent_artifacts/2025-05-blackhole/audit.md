# Audit: 2025-05-blackhole

## Reentrancy in GaugeV2 Reward Distribution
- **Location**: `GaugeV2.sol` : `getReward`
- **Mechanism**: The `getReward` function updates `rewards[msg.sender]` to 0 after transferring tokens, but makes an external call to `gaugeRewarder.onReward()` after the state update. However, the `onReward` call in `getReward(address _user)` at line 160 is protected by `onlyDistribution`, but the public `getReward()` at line 175 makes the external call after transferring reward tokens, creating a potential reentrancy vector if `gaugeRewarder` is compromised.
- **Impact**: An attacker controlling `gaugeRewarder` could re-enter to claim rewards multiple times before the `rewards` mapping is cleared.

## Division by Zero in GenesisPool Liquidity Calculation
- **Location**: `GenesisPool.sol` : `deductAmount`
- **Mechanism**: When calculating user amounts during withdrawal, the code computes `_depositerLiquidity = liquidity / 2` and then divides by this value. If `liquidity < 2`, `_depositerLiquidity` becomes 0, causing a division by zero revert.
- **Impact**: Users cannot withdraw from genesis pools with very small liquidity amounts, potentially trapping funds.

## Precision Loss in BlackClaims Reward Calculation
- **Location**: `BlackClaims.sol` : `claimAndStakeReward`
- **Mechanism**: The calculation `uint256 credit_amount = (_reward * 100)/110` truncates integer division. For small `_reward` values (e.g., 109), this results in `credit_amount = 99`, permanently losing 10 tokens that are neither claimed nor returned to the treasury.
- **Impact**: Users lose a portion of their rewards due to truncation, especially with small reward amounts.

## Missing Zero Address Check in AutoVotingEscrowManager
- **Location**: `AutoVotingEscrowManager.sol` : `enableAutoVoting`
- **Mechanism**: The function checks `uint256(int256(votingEscrow.locked(tokenId).amount)) >= minBalanceForAutovoting` but does not verify that the lock amount is positive before the int256-to-uint256 conversion. While locks shouldn't be negative, a malicious or corrupted voting escrow could return negative values.
- **Impact**: Potential underflow or incorrect balance validation if the voting escrow returns unexpected negative values.

## Unbounded Loop in RewardsDistributor
- **Location**: `RewardsDistributor.sol` : `_claim`
- **Mechanism**: The function iterates up to 50 times to calculate rewards across weeks. If a user has been inactive for more than 50 weeks, they permanently lose the ability to claim rewards from earlier epochs.
- **Impact**: Users who haven't claimed rewards for extended periods lose accumulated rewards beyond the 50-week window.

## Unsafe External Call in GaugeCL
- **Location**: `GaugeCL.sol` : `getReward`
- **Mechanism**: The function calls `farmingCenter.collectRewards()` and `claimReward()` on external contracts without verifying the return values or handling potential reentrancy from the Algebra farming contracts.
- **Impact**: If the farming center contract is compromised or behaves unexpectedly, it could manipulate reward calculations or cause denial of service.

## Integer Overflow Risk in MinterUpgradeable Emissions
- **Location**: `MinterUpgradeable.sol` : `update_period`
- **Mechanism**: The weekly emission calculations use multiplication factors like `WEEKLY_GROWTH (10300)` and `WEEKLY_DECAY (9900)` on `weekly` values. While Solidity 0.8+ prevents overflow, the logic allows `weekly` to grow exponentially in the first 14 epochs, potentially reaching values that cause downstream calculations to fail or revert.
- **Impact**: Potential denial of service if emissions grow too large for downstream contracts to handle.

## Access Control Bypass in CustomPoolDeployer
- **Location**: `CustomPoolDeployer.sol` : `onlyAuthorized`
- **Mechanism**: The `onlyAuthorized` modifier allows both the owner and any address in `authorizedAccounts` to call sensitive functions like `setPlugin`, `setFee`, and `setCommunityFee`. There's no mechanism to revoke authorization except through the owner.
- **Impact**: If an authorized account is compromised, the attacker can manipulate pool parameters, fees, and plugins without owner intervention.

## Unchecked Array Access in veNFTAPIV1
- **Location**: `veNFTAPIV1.sol` : `getAVMNFTFromAddress`
- **Mechanism**: The function creates a fixed-size array `veNFT[] memory temp = new veNFT[](1000)` and increments `count` without bounds checking. If a user has more than 1000 AVM locks, this will cause an out-of-bounds write.
- **Impact**: Potential memory corruption or denial of service for users with many AVM positions.
