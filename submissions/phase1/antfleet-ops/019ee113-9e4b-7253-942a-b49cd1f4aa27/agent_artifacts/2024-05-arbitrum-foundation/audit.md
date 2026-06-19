# Audit: 2024-05-arbitrum-foundation

# Security Audit Report

## EdgeStakingPool Blocked by Validator Whitelist
- **Location**: `src/assertionStakingPool/EdgeStakingPool.sol` : `createEdge` (interacting with `src/challengeV2/EdgeChallengeManager.sol` : `createLayerZeroEdge`)
- **Mechanism**: The `createLayerZeroEdge` function in `EdgeChallengeManager` enforces a validator whitelist when enabled:
  ```solidity
  bool whitelistEnabled = !assertionChain.validatorWhitelistDisabled();
  if (whitelistEnabled && !assertionChain.isValidator(msg.sender)) {
      revert NotValidator(msg.sender);
  }
  ```
  When `EdgeStakingPool.createEdge` invokes this function, `msg.sender` is the pool contract address. The pool is a generic staking contract, not a registered validator key, so `isValidator(pool)` returns `false`. If the validator whitelist is enabled on the assertion chain, the call reverts with `NotValidator` and the edge is never created, even though the pool holds sufficient stake.
- **Impact**: All staked funds deposited by users into an `EdgeStakingPool` are permanently locked when the validator whitelist is enabled. The pool becomes completely non-functional, and depositors can only withdraw the un-staked portion of their balance — the portion approved as stake to the challenge manager is unrecoverable. This defeats the core purpose of the trustless staking pool.

## Division by Zero in `submitBatchSpendingReport` on Arbitrum
- **Location**: `src/bridge/SequencerInbox.sol` : `submitBatchSpendingReport`
- **Mechanism**: The function unconditionally performs a division by `block.basefee` when deployed on an Arbitrum host chain:
  ```solidity
  if (hostChainIsArbitrum) {
      uint256 l1Fees = ArbGasInfo(address(0x6c)).getCurrentTxL1GasFees();
      extraGas += l1Fees / block.basefee;  // reverts if block.basefee == 0
  }
  ```
  On Arbitrum chains, `block.basefee` (the L2 base fee) is permitted to be zero, particularly on low-activity chains, during congestion resets, or early in a chain's lifetime. When `block.basefee == 0`, the division reverts, which causes the entire transaction to revert. This function is invoked from `addSequencerL2BatchImpl` during calldata batch posting and from the blob batch path, so any EOA-based sequencer batch submission (`addSequencerL2BatchFromOrigin`, `addSequencerL2BatchFromOriginDelayProof`) on an Arbitrum-deployed SequencerInbox is bricked whenever the L2 base fee is zero.
- **Impact**: Complete denial-of-service for batch submission on any Arbitrum chain where the SequencerInbox is deployed (including testnets like ArbSepolia and AnyTrust-style deployments), preventing the sequencer from posting L2 batches to the rollup whenever `block.basefee` is zero. The rollup halts because no new messages can be sequenced.
