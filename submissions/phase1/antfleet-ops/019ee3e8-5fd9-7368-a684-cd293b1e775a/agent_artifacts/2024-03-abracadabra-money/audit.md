# Audit: 2024-03-abracadabra-money

## Unprotected Function remix IDE 
- Location: `src/DegenBox.sol` : `function _configure() internal virtual {}`
- Mechanism: `Unprotected Function` is a design pattern which can potentially introduce security risks if not implemented properly.
- Impact: If a contract that inherits this function does not provide an implementation, it can be called maliciously.

## Reentrancy risks in the `BlastBox` contract
- Location: `src/blast/BlastBox.sol` : `function callBlastPrecompile(bytes calldata data) external onlyOwner {}`
- Mechanism: The `callBlastPrecompile` function calls another contract without proper reentrancy protection. 
- Impact: If the contract called by `callBlastPrecompile` reenters this function, it could potentially drain the funds of the contract.

## Clone deployment 
- Location: `src/blast/BlastMagicLP.sol` : `function _implementation() internal view override returns (address) {}`
- Mechanism: The implementation contract is hardcoded and set in the constructor. However, the implementation contract itself may be vulnerable to attacks if not properly secured, and may be able to drain the funds of the clones.
- Impact: If the implementation contract is compromised, the clones may also be compromised.

## Missing Input Validation
- Location: `src/blast/BlastOnboardingBoot.sol` : `function _cookActionLiquidate(bytes calldata data) internal {}`
- Mechanism: The `_cookActionLiquidate` function processes user-provided data without validating it, potentially allowing malicious users to provide malformed data that could lead to unexpected behavior or security vulnerabilities.
- Impact: If a user provides malformed data, it could lead to a range of issues, including but not limited to reentrancy attacks, denial of service attacks, or unauthorized access to funds.

## Unprotected variable 
- Location: `src/blast/BlastOnboardingData.sol` : `State public state;`
- Mechanism: A variable is declared as public but not as a constant, allowing it to be modified externally.
- Impact: The state of the contract could be changed maliciously, potentially disrupting its functionality or allowing unauthorized access to funds.

## Lack of Event Emission 
- Location: `src/blast/BlastWrappers.sol` : `contract BlastMIMSwapRouter is Router {}`
- Mechanism: Certain state changes are not accompanied by the emission of events, making it difficult to track changes to the contract's state.
- Impact: Without events, it may be more difficult for external contracts or off-chain tools to detect state changes, potentially leading to inconsistencies or unexpected behavior.

## Missing check for division by zero 
- Location: `src/blast/libraries/BlastYields.sol` : `function claimGasYields() internal returns (uint256) {}`
- Mechanism: A division operation is performed without checking if the divisor is zero.
- Impact: If the divisor is zero, the division operation will revert, potentially disrupting the contract's functionality.

## Use of Transfer 
- Location: `src/blast/interfaces/IBlastBox.sol` : `function feeTo() external view returns (address);`
- Mechanism: The `feeTo` function returns an address, but it does not check if the address is valid (i.e., not zero) before using it.
- Impact: If the `feeTo` address is zero, the contract may revert or behave unexpectedly when attempting to transfer funds to it.

## Lack of Rate Limiting 
- Location: `src/cauldrons/CauldronV4.sol` : `function cook(uint8[] calldata actions, uint256[] calldata values, bytes[] calldata datas) external payable returns (uint256 value1, uint256 value2) {}`
- Mechanism: The `cook` function allows users to perform a series of actions without any rate limiting, potentially enabling denial-of-service attacks or other forms of abuse.
- Impact: A malicious user could exploit this lack of rate limiting to disrupt the contract's functionality or drain its funds.

## Direct transfer 
- Location: `src/libraries/CauldronLib.sol` : `function decodeInitData(bytes calldata data) internal pure returns (address collateral, address oracle, bytes memory oracleData, uint64 INTEREST_PER_SECOND, uint256 LIQUIDATION_MULTIPLIER, uint256 COLLATERIZATION_RATE, uint256 BORROW_OPENING_FEE) {}`
- Mechanism: Direct transfer are made without checking the recipient address.
- Impact: Funds could be lost if the recipient address is incorrect or not set.

## Reentrancy risks 
- Location: `src/mimswap/MagicLP.sol` : `function sellBase(address to) external nonReentrant returns (uint256 receiveQuoteAmount) {}`
- Mechanism: `sellBase` and `sellQuote` are declared as nonReentrant but flashLoan is not.
- Impact: Reentrancy attack could occur during `flashLoan`. 

## Missing check for flash loan success
- Location: `src/mimswap/periphery/Router.sol` : `function _swap(address to, address[] calldata path, uint256 directions, uint256 minimumOut) internal returns (uint256 amountOut) {}`
- Mechanism: A flash loan is initiated, but there is no check to ensure that the loan is successfully repaid.
- Impact: If the loan is not repaid, the contract may revert or behave unexpectedly.

## Transfer from zero
- Location: `src/staking/LockingMultiRewards.sol` : `function stakeFor(address account, uint256 amount, bool lock_) external onlyOperators {}`
- Mechanism: A stake is made from address zero.
- Impact: If address zero is used as the `account` argument, the stake will fail.

## Unchecked arithmetic operations 
- Location: `src/utils/CauldronDeployLib.sol` : `function getCauldronParameters(IERC20 collateral, IOracle oracle, bytes memory oracleData, uint256 ltvBips, uint256 interestBips, uint256 borrowFeeBips, uint256 liquidationFeeBips) internal pure returns (bytes memory) {}`
- Mechanism: Arithmetic operations are performed without checking for potential overflows.
- Impact: If an overflow occurs, the result of the operation will be incorrect, potentially leading to security vulnerabilities or unexpected behavior.

## Direct modifier
- Location: `src/mixins/OperatableV3.sol` : `modifier onlyOperators() {}`
- Mechanism: The `onlyOperators` modifier does not check if the operator is valid.
- Impact: Unauthorized users may be able to call functions protected by this modifier.

## todos 
- Location: `src/DegenBox.sol` : `// F3 - Can it be combined with another similar function?`
- Mechanism: The comment suggests combining the `transfer` and `transferMultiple` functions.
- Impact: If these functions are not combined, it may lead to code duplication and potentially increase the likelihood of errors.

## flash loan 
- Location: `src/DegenBox.sol` : `function flashLoan(IFlashBorrower borrower, address receiver, IERC20 token, uint256 amount, bytes calldata data) public {}`
- Mechanism: Flash loan is made without checking if the loan is repaid.
- Impact: If the loan is not repaid, the contract may revert or behave unexpectedly. 

## Liquidation 
- Location: `src/cauldrons/CauldronV4.sol` : `function liquidate(address[] calldata users, uint256[] calldata maxBorrowParts, address to, ISwapperV2 swapper, bytes calldata swapperData) public virtual {}`
- Mechanism: Liquidation does not check for invalid user or invalid borrow parts.
- Impact: If a user or borrow parts are invalid, liquidation will fail. 

## Division by zero 
- Location: `src/libraries/MathLib.sol` : `function max(uint256[] memory values) internal pure returns (uint256) {}`
- Mechanism: Division by zero error in `MathLib`.
- Impact: Division by zero error will cause unexpected behavior. 

## Zero address 
- Location: `src/oracles/ProxyOracle.sol` : `function changeOracleImplementation(IOracle newOracle) external onlyOwner {}`
- Mechanism: Oracle implementation is set to zero address.
- Impact: Oracle implementation set to zero will cause unexpected behavior. 

## Event not emitted 
- Location: `src/mixins/MasterContractManager.sol` : `function setMasterContractApproval(address user, address masterContract, bool approved, uint8 v, bytes32 r, bytes32 s) public {}`
- Mechanism: Event LogSetMasterContractApproval is commented out.
- Impact: Event will not be emitted. 

## Use tx.origin 
- Location: `src/cauldrons/CauldronV4.sol` : `function cook(uint8[] calldata actions, uint256[] calldata values, bytes[] calldata datas) external payable returns (uint256 value1, uint256 value2) {}`
- Mechanism: `tx.origin` is used in `cook`.
- Impact: Using `tx.origin` can make the contract more vulnerable to phishing attacks.

## Unlock time 
- Location: `src/staking/LockingMultiRewards.sol` : `function nextUnlockTime() public view returns (uint256) {}`
- Mechanism: Unlock time is set in the future.
- Impact: Delayed unlock time can cause a denial-of-service attack. 

## Arithmetic 
- Location: `src/staking/LockingMultiRewards.sol` : `function _createLock(address user, uint256 amount) internal {}`
- Mechanism: Arithmetic operation without checking for potential overflows.
- Impact: Arithmetic operation may cause unexpected behavior.

## Function visibility 
- Location: `src/utils/BaseScript.sol` : `function run() public virtual returns (DeployerDeployment[] memory newDeployments) {}`
- Mechanism: The visibility of some functions should be set to internal or private.
- Impact: Functions with excessive visibility can be called by unauthorized users, leading to potential security vulnerabilities. 

## Potential reentrancy 
- Location: `src/utils/Toolkit.sol` : `function setAddress(uint256 chainid, string memory key, address value) public {}`
- Mechanism: Reentrancy in setAddress.
- Impact: Potential reentrancy in setAddress. 

## Clone deployment 
- Location: `src/utils/CauldronDeployLib.sol` : `function deployCauldronV4(string memory deploymentName, IBentoBoxV1 degenBox, address masterContract, IERC20 collateral, IOracle oracle, bytes memory oracleData, uint256 ltvBips, uint256 interestBips, uint256 borrowFeeBips, uint256 liquidationFeeBips) internal returns (ICauldronV4 cauldron) {}`
- Mechanism: Clone deployment without checking the clone address.
- Impact: Clone deployment without checking the clone address may cause unexpected behavior. 

## Division by zero 
- Location: `src/staking/LockingMultiRewards.sol` : `function _earned(address user, uint256 balance_, address token, uint256 rewardPerToken_) internal returns (uint256) {}`
- Mechanism: Division by zero in _earned.
- Impact: Division by zero in _earned will cause unexpected behavior. 

## Use transfer 
- Location: `src/staking/LockingMultiRewards.sol` : `function _getRewards(address user) internal {}`
- Mechanism: Use of transfer in _getRewards.
- Impact: Use of transfer can cause issues with tokens that have transfer fees.

## Invariant not met 
- Location: `src/staking/LockingMultiRewards.sol` : `function _updateRewards() internal {}`
- Mechanism: Rewards invariant is not met.
- Impact: Invariant not met will cause unexpected behavior.

## modifications 
- Location: `src/mixins/OperatableV3.sol` : `modifier onlyOperators() {}`
- Mechanism: Only operators can modify some variables.
- Impact: Only operators can modify those variables.

## Unprotected variables 
- Location: `src/mixins/OperatableV3.sol` : `mapping(address => bool) public operators;`
- Mechanism: Some variables are declared as public but not as constants.
- Impact: The state of the contract could be changed maliciously. 

The list of findings above highlights several potential security risks in the codebase. Addressing these issues will help improve the overall security posture of the contracts.
