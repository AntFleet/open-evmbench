# Audit: 2025-04-virtuals

 ## Reward share settings can exceed denominator and underflow
- Location: AgentRewardV2.sol : `_distributeAgentRewards`, `_distributeProtocolRewards`; AgentRewardV3.sol : `_distributeAgentReward`, `_distributeProtocolRewards`
- Mechanism: `protocolShares`, `contributorShares`, and `stakerShares` are `uint16` values set via `setRewardSettings` without any upper-bound check against `DENOMINATOR` (10000). The code later subtracts the computed share from the raw amount, e.g. `reward.validatorAmount = amount - reward.contributorAmount` and `balance = amount - protocolAmount`. When any share is configured above 10000, the calculated share exceeds the original amount and the subtraction underflows.
- Impact: A compromised or misconfigured `GOV_ROLE` bricks all subsequent reward distributions, permanently locking reward funds in the contract.

## AgentRewardV3 claims permanently revert on zero stake or zero proposals
- Location: AgentRewardV3.sol : `getClaimableStakerRewards`, `getClaimableValidatorRewards`
- Mechanism: Both functions divide by `agentReward.totalStaked` and `agentReward.totalProposals` without checking for zero. `_distributeAgentReward` records these values at distribution time and pushes an `AgentReward` even when `totalStaked` is 0 (unstaked/private agent) or `totalProposals` is 0 (new agent). Because the claim loops sequentially over all unclaimed rewards, a single such reward makes the entire transaction revert.
- Impact: All future staker and validator rewards for the affected agent become permanently unclaimable, locking those funds.

## AgentRewardV2 staker claims DoS when delegatee had zero votes
- Location: AgentRewardV2.sol : `_getClaimableStakerRewardsAt`
- Mechanism: The function returns early only when `delegatee == address(0)`, but otherwise divides `validatorGroupRewards` by `IERC5805(stakingAddress).getPastVotes(delegatee, mainReward.blockNumber)`. If the delegatee had zero voting power at the reward snapshot, the division reverts. `_getClaimableStakerRewards` iterates sequentially over all unclaimed rewards, so one zero-vote reward blocks every later reward for that staker and virtualId.
- Impact: A staker whose delegatee had no votes at a single snapshot loses the ability to claim all subsequent rewards for that agent.

## Genesis success callback is re-executable
- Location: Genesis.sol : `onGenesisSuccess`
- Mechanism: The function has no "succeeded" flag; it only skips token creation on replays via `isFirstLaunch = (agentTokenAddress == 0)`. On every call it still processes virtual-token refunds and overwrites `claimableAgentTokens` for arbitrary distribution addresses. The agent-token balance check passes on replays because the first call records claims but does not transfer tokens.
- Impact: An `OPERATION_ROLE` account can call `onGenesisSuccess` repeatedly to over-allocate agent tokens to arbitrary addresses, creating conflicting claims and draining the contract once recipients claim.

## Elo calculation can underflow and DoS maturity updates
- Location: EloCalculator.sol : `battleElo`
- Mechanism: The function returns `currentRating + eloA - 1000`. `eloA` starts at 1000 and decreases when the `battles` array indicates losses. If `eloA` falls below 1000 by more than `currentRating`, the subtraction underflows and reverts in Solidity 0.8.
- Impact: A model proposal that loses Elo battles with low starting maturity can make `AgentDAO.getMaturity` and `ServiceNft.updateImpact` revert, blocking proposal execution and downstream reward calculations.

## AgentFactoryV2 ignores failed asset-token transfers
- Location: AgentFactoryV2.sol : `executeApplication`
- Mechanism: The function uses `IERC20(assetToken).transfer(token, initialAmount)` instead of `safeTransfer`. If `assetToken` is a non-standard token that returns `false` on failure rather than reverting, the failure is ignored and execution continues.
- Impact: An application can be executed without the initial asset tokens actually reaching the agent token contract, bootstrapping a "phantom" agent with no backing liquidity.

## FERC20 owner can burn arbitrary holder balances
- Location: FERC20.sol : `burnFrom`
- Mechanism: `burnFrom` is `onlyOwner` and directly subtracts the specified amount from `_balances[user]` without checking allowance or token ownership.
- Impact: The owner contract (the bonding curve) can arbitrarily destroy any holder's tokens, including tokens held in pair addresses or user wallets.

## AgentToken max-wallet and max-transaction limits are never enforced
- Location: AgentToken.sol : `_pretaxValidationAndLimits`
- Mechanism: `_tokenSupplyParams` decodes `maxTokensPerWallet` and `maxTokensPerTxn`, but `_pretaxValidationAndLimits` only validates balance and `fundedDate`. No code path ever checks transfer size or recipient wallet balance against these parameters.
- Impact: The intended anti-whale and bot-protection limits are completely ineffective; large holders can freely accumulate or dump tokens.

## AgentToken tax rates can be increased beyond the stated design
- Location: AgentToken.sol : `setProjectTaxRates`
- Mechanism: The function comment states rates are "subject to only ever decreasing," but the implementation simply assigns the new values without enforcing a decrease-only invariant.
- Impact: The owner or factory can raise buy/sell tax to 10000 basis points, making sells impossible and effectively freezing holder funds inside the token.

## AgentToken tax auto-swap accepts zero slippage
- Location: AgentToken.sol : `_swapTax`
- Mechanism: The auto-swap calls `swapExactTokensForTokensSupportingFeeOnTransferTokens` with `amountOutMin` hard-coded to `0`.
- Impact: MEV bots can sandwich the swap, stealing tax proceeds and reducing or eliminating the project's collected taxes.

## ServiceNft impact updates are unauthenticated
- Location: ServiceNft.sol : `updateImpact`
- Mechanism: `updateImpact` is `public` and can be called by anyone for any `tokenId`. It recalculates and writes `_impacts[proposalId]` and `_impacts[datasetId]` based on the current core service and `datasetImpactWeight`, even for dataset tokens or after the initial mint.
- Impact: Any user can corrupt service/dataset impact values or exploit subsequent changes to `datasetImpactWeight` to alter reward distribution weights.

## Airdrop lacks array-length and amount-sum validation
- Location: Airdrop.sol : `airdrop`
- Mechanism: The function does not verify `recipients.length == amounts.length` and does not check that the sum of `amounts` equals `_total`. It uses `amounts.length` as the loop bound and reads `recipients` at matching offsets.
- Impact: A caller can pass mismatched arrays, causing transfers to unintended addresses (or `address(0)` if reading past the array) and leaving excess tokens stuck in the contract.

## ContributionNft ownerOf violates ERC-721 for non-existent tokens
- Location: ContributionNft.sol : `ownerOf`
- Mechanism: `ownerOf` overrides ERC-721 and returns `_ownerOf(tokenId)`, which yields `address(0)` for non-existent tokens instead of reverting as the standard requires.
- Impact: Contracts that expect the standard revert behavior may treat burned or non-existent contribution tokens as owned by the zero address, leading to incorrect access-control or reward calculations.

## AgentRewardV2 protocol/validator withdrawals lack reentrancy protection
- Location: AgentRewardV2.sol : `withdrawProtocolRewards`, `withdrawValidatorPoolRewards`
- Mechanism: Both functions transfer reward tokens before setting `protocolRewards`/`validatorPoolRewards` to zero and do not use the contract's `noReentrant` modifier.
- Impact: If the `onlyGov` recipient is a malicious contract, it can reenter before the balance is zeroed and drain the respective reward pool.

## AgentRewardV2 service-claim path lacks reentrancy guard
- Location: AgentRewardV2.sol : `claimAllRewards`, `_claimServiceRewards`
- Mechanism: `claimAllRewards` is not nonReentrant, and the internal `_claimServiceRewards` performs a token transfer after state updates without any reentrancy protection.
- Impact: If `rewardToken` has transfer hooks or is malicious, a reentrant call can re-enter `claimAllRewards` and repeat the claim flow, enabling gas griefing or unexpected state interactions.
