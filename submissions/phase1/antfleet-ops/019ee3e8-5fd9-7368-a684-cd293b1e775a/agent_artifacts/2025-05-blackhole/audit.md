# Audit: 2025-05-blackhole

## AlgebraPoolAPI/PoolInfo storage can be overflowed
- Location: `AlgebraPoolAPI.sol` : `function getAllPoolInfo(address[] calldata _pools) external view returns(PoolInfo[] memory infos)`
- Mechanism: The storage variable `infos` is declared to have a dynamic length, which is set when the function is called. If an attacker can manipulate this length, after some time it can fit arbitrary amounts of data in that slot and potentially overflow the slot, which could lead to potential vulnerabilities.
- Impact: Potential vulnerabilities depending on how the contract is designed to modify or read storage. 

## PoolFactory's gauge registration is vulnerable
- Location: `AlgebraPoolAPI.sol` : ` function setFactory(address _newFactory) external`
- Mechanism: Private variable `gauges` in `AlgebraPoolAPI.SwapRouteHelperData` is declared but never initialized. 
- Impact: Reentrancy possible if this variable is accessed in a modifying method without initialization, which is only reachable through `_setGaugeAsCommunityFeeReceiver`. This could further allow an attacker to drain contract funds.

## Pair API does not lock the incentive tokens
- Location: `AlgebraPoolAPI.sol` : ` function getPoolInfo(address _pool) external view returns(PoolInfo memory info)`
- Mechanism: Potential Reentrancy Attack is possible if we do not make sure to lock incentive tokens. Because, the map variables allow arbitrary access through unchecked `token` value.
- Impact: A malicious caller can potentially drain contract funds using flash loan tactics, whether by Reentrancy Attack or direct theft if incorrectly implemented. 

## getReward function in GaugeV2 is vulnerable to reentrancy attack 
- Location: `GaugeV2.sol` : `function getReward(address _user) public nonReentrant updateReward(_user) `
- Mechanism:  Potential Reentrancy Attack is possible if we do not update balance when emitting event. Because, the map variables allow arbitrary access through unchecked `_user` value.
- Impact: A malicious caller can potentially drain contract funds using flash loan tactics, whether by Reentrancy Attack or direct theft if incorrectly implemented.

## veNFTAPIV1.setRewardDisitributor() has wrong argument ordering 
- Location: `veNFTAPIV1.sol` : `function setRewardDisitributor(address _rewarddistro) external  {`
- Mechanism: The code is written as: `IRewardsDistributor(_rewardDistro).voting_escrow() == voter._ve()` but the setter function have `(IRewardsDistributor(_rewarddistro).voting_escrow() == voter._ve())`. well-ordered. As intended, changed `voter` to type (`IRewardsDistributor`) not created yet
- Impact: this would lead to reverted transfers

## veNFTAPIV1.setAddress() lacks input check
- Location: `veNFTAPIV1.sol` : `function setOwner(address _owner) external {`
- Mechanism: The contract `veNFTAPIV1.setAddress()` hasn't added a check to avoid setting `owner` to zero.
- Impact: It could allow an attacker to potentially escalate their privilege by exploiting the contract.

## TokenHandler does not handle cases where streams enable Methods maybe broken
- Location: `AlgebraPoolAPIStorage.sol` : `function updateTokenVolatilityBucket(address _token, uint256 bucketId) external`
- Mechanism: The method is declared onlyGovernance but no checks are put in place to check whether the new volatility bucket is less than or equal to the maximum number of buckets.
- Impact: If this is the case, the function may not behave as expected.
