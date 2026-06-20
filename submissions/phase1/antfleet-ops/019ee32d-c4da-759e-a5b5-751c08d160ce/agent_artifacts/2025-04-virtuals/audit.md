# Audit: 2025-04-virtuals

Here is the audit of the provided smart-contracts codebase. Below are the security vulnerabilities identified during the review.

---

## 1. Zero Access Control on `updateImpact` Wipes Out Service and Dataset NFT Impacts
- **Location**: `ServiceNft.sol` : `updateImpact`
- **Mechanism**: The `updateImpact` function is defined as `public` and contains zero access control validations (such as `onlyOwner` or requiring caller to be the VIRTUAL DAO). Furthermore, when evaluated with a previously minted `proposalId`, `prevServiceId` will resolve as `proposalId` itself (since it was already stored in `_coreServices` during the mint). This makes `_maturities[proposalId] > _maturities[prevServiceId]` evaluate to `false`, forcing `rawImpact = 0`.
- **Impact**: Any attacker can call `updateImpact` on any existing `proposalId`, which instantly overwrites both `_impacts[proposalId]` and its associated `_impacts[datasetId]` (if applicable) to `0`. This permanently wipes out the impact metric of the Service and Dataset NFTs, making it impossible for creators to claim their respective rewards in `Minter.sol` and `AgentRewardV2.sol`.

---

## 2. Division by Zero in V3 Rewards Bricks All Claims If Total Proposals or Staking is Zero
- **Location**: `AgentRewardV3.sol` : `getClaimableStakerRewards` / `getClaimableValidatorRewards`
- **Mechanism**: In V3 reward claims, the loop to evaluate staker and validator payouts processes each historical reward index consecutively. If an agent is initialized but has not received any proposals (meaning `totalProposals == 0`), or has zero stakers (`totalStaked == 0`) during a reward distribution event, the mathematical operations:
  `stakerReward = (stakerReward * uptime) / agentReward.totalProposals;` OR `validatorReward = (agentReward.stakerAmount * staked) / agentReward.totalStaked;`
  will fail due to division by zero.
- **Impact**: Because the claiming operations (`claimStakerRewards` and `claimValidatorRewards`) iterate sequentially through all past undistributed rewards in a single transaction, a single period with `totalProposals == 0` or `totalStaked == 0` will permanently trigger a revert, forever locking all users out of claiming their rewards for all epochs on that `virtualId`.

---

## 3. Denial of Service (DoS) in V2 Reward Distributions via Validator Overflow
- **Location**: `AgentRewardV2.sol` : `_distributeValidatorRewards`
- **Mechanism**: The `_distributeValidatorRewards` execution iterates through every registered validator using `nft.validatorCount(virtualId)`. However, `AgentVeToken.stake` permits any staking user to designate any arbitrary address as their delegatee. Upon doing so, this delegatee is permanently pushed to the NFT's active validator array using `_addValidator` without limit.
- **Impact**: An attacker can easily flood the validator list on any given agent by creating thousands of staking accounts and delegating to unique burner addresses. This inflates the validator array size, making the loop in `_distributeValidatorRewards` consume gas in excess of the EVM block gas limit, permanently bricking `distributeRewards` and `distributeRewardsForAgents` for that agent.

---

## 4. Wrong Units / Math Error in `AgentTax.sol` DCA Conversions
- **Location**: `AgentTax.sol` : `dcaSell`
- **Mechanism**: In `dcaSell`, the minimum expected output value on swaps is evaluated as:
  `uint256 minOutput = ((amountToSwap * (DENOM - slippage)) / DENOM);`
  `amountToSwap` is denominated in `taxToken` units, while `minOutput` is ultimately supplied as the `amountOutMin` parameter inside `router.swapExactTokensForTokens` (corresponding to output in `assetToken`). This represents a direct comparison of two different assets without scaling for their exchange rate or decimals.
- **Impact**: 
  - If 1 `taxToken` is worth less than 1 `assetToken` (e.g. standard tokens vs VIRTUAL), `minOutput` demands a larger token output than possible, causing `dcaSell` to always revert.
  - If 1 `taxToken` is worth more than 1 `assetToken`, `minOutput` evaluates to a negligible amount, offering practically zero slippage protection and exposing the protocol to severe front-running/sandwich losses of tax funds.

---

## 5. Division by Zero Locks Historical Staker Claims in `AgentRewardV2`
- **Location**: `AgentRewardV2.sol` : `_getClaimableStakerRewardsAt`
- **Mechanism**: When querying staker claims, `_getClaimableStakerRewardsAt` executes `(validatorGroupRewards * tokens) / votes`. If a user held a delegatee historically but had exactly `0` token balance at a specific reward block, the total active `votes` of that delegatee at that block could also return `0`.
- **Impact**: Performing `(0 * 0) / 0` triggers a division-by-zero revert. Because the claiming sequence loops across all previous epochs, a revert on any historical epoch will block the user from navigating the loop, permanently bricking their ability to claim any valid staking rewards earned in other epochs.

---

## 6. Underflow Reverts in DAO ELO Calculations Bricks Voting
- **Location**: `AgentDAO.sol` : `_updateMaturity`, `EloCalculator.sol` : `battleElo`
- **Mechanism**: The ELO calculation starts `eloA` and `eloB` at 1000. If battle outcomes evaluate to a negative shift for `eloA`, its value decreases below 1000. When calculating the updated rating output:
  `return currentRating + eloA - 1000;`
  An underflow will occur if the decrease in `eloA` (e.g., -101 ELO) exceeds the `currentRating` of the service (which starts at 100), since `currentRating + eloA < 1000`.
- **Impact**: In Solidity `^0.8.0`, arithmetic underflow automatically reverts. Any vote cast with metadata that results in a net ELO loss greater than the service's starting rating will revert the entire `_castVote` call, permanently preventing users from voting on certain proposals.
