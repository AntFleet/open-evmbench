# Audit: 2024-05-arbitrum-foundation

## <Vulnerability>
- Location: `src/assertionStakingPool/AbsBoldStakingPool.sol` : `function depositIntoPool(uint256 amount) external {... }`
- Mechanism: Reentrancy
- Impact: An attacker can reenter `depositIntoPool` before the internal state is updated. The attacker will be able to infinitely increase the `depositBalance`. This can lead to incorrect results when staking and potentially allow the attacker to drain the pool's funds. 
- Impact Description: There are multiple problems with depositIntoPool: it's missing reentrancy protection, additional gas costs associated with transferring a token, reentrancy vulnerabilities when implementing ERC20 tokens,...)
## 
# <short title>
## < AbsBoldStakingPool depositIntoPool function does not prevent reentrancy attacks, allowing an attacker to overwrite its deposit balance and withdraw more funds.


## <Vulnerability>
- Location: `src/bridge/Bridge.sol` : `function executeCall(address to, uint256 value, bytes calldata data) external override returns (bool success, bytes memory returnData) {... }`
- Mechanism: Reentrancy 
- Impact: The `executeCall` function in the Bridge contract is vulnerable to a reentrancy attack, allowing an attacker to drain the contract's funds by repeatedly calling `executeCall` before the internal state can be updated.
## 
# <short title>
## < Bridge executeCall function does not prevent reentrancy attacks.


## <Vulnerability>
- Location: `src/bridge/AbsOutbox.sol` : `function executeTransaction(bytes32[] calldata proof, uint256 index, address l2Sender, address to, uint256 l2Block, uint256 l1Block, uint256 l2Timestamp, uint256 value, bytes calldata data) external {... }`
- Mechanism: Reentrancy 
- Impact: The `executeTransaction` function in the Outbox contract is vulnerable to reentrancy attacks, allowing an attacker to execute the same transaction multiple times, potentially leading to unintended behavior or fund drainage.
## 
# <short title>
## < Outbox executeTransaction function does not prevent reentrancy attacks.


## <Vulnerability>
- Location: `src/rollup/Assertion.sol`
- Location: `src/bridge/IBridge.sol`
- Location: `src/bridge/ISequencerInbox.sol`
- Mechanism: Courtesy of unimplemented functions
- Impact: Several functions are declared but not implemented, including `migrateStake`, `getRequest`, and `assertionHash`. These missing implementations can lead to unintended behavior, errors, or vulnerabilities when called.
## 
# <short title>
## < Rollup Assertion and Bridge contracts contain unimplemented functions that may be called.


## <Vulnerability>
- Location: `src/challengeV2/EdgeChallengeManager.sol`
- Mechanism: Unauthorized Edge Creation
- Impact: An unauthorized account may attempt to create an edge that claims an assertion using `createLayerZeroEdge` without going through the proper validation process, potentially allowing the creation of an invalid edge.
## 
# <short title>
## < EdgeChallengeManager createLayerZeroEdge does not properly restrict or validate the challenge edge creation.


The final answer is: 
<short title>
- Location: `src/assertionStakingPool/AbsBoldStakingPool.sol` : `function createAssertion(AssertionInputs calldata assertionInputs) external {... }`
- Mechanism: Logic Errors
- Impact: Missing validation checks for assertion inputs, potentially leading to incorrect assertions being created.
## 
# <short title>
## < AbsBoldStakingPool createAssertion function does not properly validate its assertion inputs.
