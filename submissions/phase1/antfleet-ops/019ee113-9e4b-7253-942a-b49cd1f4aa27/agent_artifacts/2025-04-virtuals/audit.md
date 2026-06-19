# Audit: 2025-04-virtuals

# Smart Contract Security Audit Findings

## Critical: LP Value Oracle Manipulation in Reward Distribution
- Location: `contracts/AgentRewardV3.sol` : `getLPValue` and `distributeRewards`
- Mechanism: The `getLPValue` function returns `IERC20(rewardToken).balanceOf(lp)`, using the raw balance of the reward token held by the LP pool as a measure of the virtual's value. This balance is easily manipulated by anyone donating tokens directly to the LP address. In `distributeRewards`, the share of each virtual is calculated as `(lpValues[i] * balance) / totalLPValues`. An attacker can inflate the LP balance for a specific virtual to capture a disproportionate share of the reward distribution.
- Impact: An attacker can manipulate the reward distribution to receive more rewards than entitled, draining the reward pool. They can sandwich the `distributeRewards` call by inflating the LP balance right before and withdrawing/dumping the rewards after.

## Critical: Stuck Rewards Due to State Update Before Transfer
- Location: `contracts/AgentRewardV3.sol` : `claimStakerRewards`, `claimValidatorRewards`, `claimAllStakerRewards`, `claimAllValidatorRewards`
- Mechanism: These functions update the `claim.rewardCount` and `claim.totalClaimed` state variables *before* executing the `safeTransfer` of reward tokens. If the transfer fails (e.g., insufficient contract balance, token blacklisting, or a revert in a hook), the state is already updated. The `getClaimableStakerRewards` and `getClaimableValidatorRewards` functions use `claim.rewardCount` as the starting index for the loop. Once `rewardCount` is advanced past a failed claim, the user permanently loses access to those rewards.
- Impact: Users can permanently lose accrued rewards if the contract has insufficient balance or if the token transfer fails for any reason. There is no way to recover or re-claim these rewards.

## High: Underflow Risk in Reward Settings
- Location: `contracts/AgentRewardV3.sol` : `setRewardSettings` and `_distributeAgentReward`
- Mechanism: The `setRewardSettings` function does not validate that `protocolShares_ + stakerShares_ <= DENOMINATOR`. In `_distributeAgentReward`, `stakerAmount = (amount * settings.stakerShares) / DENOMINATOR` and `validatorAmount = amount - stakerAmount`. If `stakerShares_ > DENOMINATOR` (e.g., 20000), `stakerAmount` will exceed `amount`, causing an underflow in the subtraction.
- Impact: An admin (or compromised gov key) can set invalid reward settings that cause arithmetic underflow, potentially freezing funds or enabling manipulation of reward calculations.

## High: Only Latest Main Reward Can Be Distributed
- Location: `contracts/AgentRewardV2.sol` : `_distributeAgentRewards`
- Mechanism: The function retrieves the reward to distribute using `_rewards[virtualId][_rewards[virtualId].length - 1]` (the last element) and checks if `reward.mainIndex == mainRewardIndex`. If a new main reward is created via `distributeRewards` before the previous one is fully distributed via `distributeRewardsForAgents`, the last element in the virtual's rewards array will correspond to the new main reward. The function will then skip the old main reward, leaving it permanently undistributed.
- Impact: Rewards for main reward rounds can become permanently stuck and undistributed if the admin creates a new round before finishing the previous one. Users will lose access to their share of those rewards.

## High: Missing Proposal State Check in Contribution Minting
- Location: `contracts/contribution/ContributionNft.sol` : `mint`
- Mechanism: The `mint` function only checks that the caller is the proposer of the proposal, but does not verify that the proposal has succeeded or is even active. A failed, canceled, or pending proposal can be used to mint a contribution NFT.
- Impact: Anyone can mint contribution NFTs for failed proposals, potentially claiming rewards, inflating metrics, or disrupting the service NFT and reward distribution systems that rely on valid contribution NFTs.

## High: Inconsistent Settings in Reward Distribution
- Location: `contracts/AgentRewardV2.sol` : `distributeRewards` vs `distributeRewardsForAgents`
- Mechanism: `distributeRewards` uses `getRewardSettings()` (latest) to prepare agent rewards, but `distributeRewardsForAgents` also uses `getRewardSettings()` (latest) for distribution. If reward settings are changed between the two calls, the distribution will use different parameters than what was used during preparation. Additionally, `getPastRewardSettings` exists but is not used, leading to potential inconsistencies with historical reward queries.
- Impact: Reward distributions can be calculated incorrectly if settings change between preparation and distribution, leading to loss of funds or incorrect reward allocation.

## High: Tax Calculation Error in Router
- Location: `contracts/fun/FRouter.sol` : `sell` and `buy`
- Mechanism: The tax is calculated as `uint256 txFee = (fee * amountOut) / 100;` in `sell` and `(fee * amountIn) / 100;` in `buy`. The `fee` is intended to be in basis points (e.g., 100 = 1%) but is divided by 100. If `sellTax` or `buyTax` is set to a value greater than 100 (e.g., 500 for 5%), the `txFee` will exceed the amount, and the calculation `amount = amountOut - txFee` will underflow. Furthermore, there is no validation in `FFactory.setTaxParams` to prevent values > 100.
- Impact: If taxes are set to realistic values (e.g., 500 for 5%), all sells and buys will revert, or worse, underflow and revert silently. This can brick the bonding curve functionality.

## High: Cancelled Genesis Locks Participant Funds
- Location: `contracts/genesis/Genesis.sol` : `cancelGenesis` and `onGenesisFailed`
- Mechanism: If `cancelGenesis` is called, `isCancelled` is set to true. However, participants have no way to withdraw their virtual tokens. `onGenesisFailed` requires the genesis to be ended (`whenEnded`) and not cancelled (`whenNotCancelled`). `participate` requires the genesis to be active (`whenActive`). If cancelled before the end time, participants are stuck: they cannot get refunds and cannot claim agent tokens (since the agent token is never launched).
- Impact: Participants can permanently lose their contributed virtual tokens if the genesis is cancelled before the end time.

## High: State Update Before Transfer in Service Reward Claims
- Location: `contracts/AgentRewardV2.sol` : `_claimServiceRewards`
- Mechanism: The function updates `serviceReward.totalClaimed` and `childReward.totalClaimedParent` *before* performing the `safeTransfer` of reward tokens. The function lacks the `noReentrant` modifier (unlike `_claimStakerRewards` and `_claimValidatorRewards`). If the reward token is a hook-enabled token (e.g., ERC777) or if the transfer fails, the state is updated but tokens are not received, or reentrancy could allow double-claiming.
- Impact: Users can lose rewards if the transfer fails, or an attacker could exploit reentrancy to claim the same rewards multiple times.

## Medium: Division by Zero in Reward Calculations
- Location: `contracts/AgentRewardV2.sol` : `_getClaimableStakerRewardsAt`
- Mechanism: The function calculates `(((validatorGroupRewards * tokens) / votes) * stakerShares) / DENOMINATOR`. If `votes` (the delegatee's past votes) is zero, the division by zero will revert. This can happen if a validator was added but never received any vote delegations, or if all delegators withdrew before the reward block.
- Impact: Reward claims can revert for users who delegated to validators with no votes, preventing them from claiming their share of rewards.

## Medium: Division by Zero in Contributor Reward Distribution
- Location: `contracts/AgentRewardV2.sol` : `_distributeContributorRewards`
- Mechanism: The function calculates `impactAmount = (reward.coreAmount * serviceReward.impact) / _rewardImpacts[reward.id][core]`. If all services for a core have zero impact, `_rewardImpacts[reward.id][core]` is zero, causing a division by zero revert.
- Impact: If a core has services with zero impact, the reward distribution for that agent will revert, potentially blocking all reward claims for that agent.

## Medium: Unbounded Validator List Growth
- Location: `contracts/virtualPersona/AgentVeToken.sol` : `stake`
- Mechanism: The `stake` function calls `registry.addValidator(virtualId, delegatee)`, which appends to the validator array. Anyone can stake with a new delegatee address, adding a new validator. There is no limit on the number of validators per virtual.
- Impact: An attacker can bloat the validator list with many addresses (including contracts that revert on `getPastVotes` or similar), making `totalUptimeScore` and validator iteration in `AgentRewardV2._distributeValidatorRewards` extremely expensive or unfeasible due to gas limits, effectively blocking reward distribution.

## Medium: Unprotected Public Impact Update
- Location: `contracts/contribution/ServiceNft.sol` : `updateImpact`
- Mechanism: The `updateImpact` function has no access control. Anyone can call it to recalculate and update the impact of a service NFT. The function overwrites `_impacts[proposalId]` and potentially `_impacts[datasetId]`, which are used for reward distribution.
- Impact: An attacker can manipulate service impact values to influence reward distribution in `AgentRewardV2._distributeContributorRewards`, potentially stealing rewards or griefing other contributors.

## Medium: Weak Token Compatibility Check
- Location: `contracts/virtualPersona/AgentFactoryV4.sol` : `isCompatibleToken` and `initFromToken`
- Mechanism: The `isCompatibleToken` function only checks that the token contract has the required function selectors using `try/catch`. Any malicious contract that implements these functions with arbitrary logic will pass the check.
- Impact: An attacker can deploy a malicious ERC20-like contract that passes the compatibility check but contains hidden logic (e.g., reentrancy hooks, fake total supply) to exploit the factory or steal liquidity during the `addLiquidity` call in `_executeApplication`.

## Medium: Missing Reentrancy Protection on External Calls
- Location: `contracts/AgentInference.sol` : `prompt` and `promptMulti`
- Mechanism: Both functions use `nonReentrant`, but they perform external calls to `token.safeTransferFrom` and `agentNft.virtualInfo`. The `safeTransferFrom` is protected by the nonReentrant modifier, but the `agentNft.virtualInfo` call is an external read. More importantly, the balance check `require(token.balanceOf(sender) >= total, "Insufficient balance")` is a snapshot check that can be outdated if the token has hooks or if the state changes. However, the nonReentrant modifier prevents reentrancy.
- Impact: Generally safe due to nonReentrant, but the logic in `promptMulti` has a bug where `prevAgentId` is never updated (see below).

## Medium: No Decreasing Enforcement for Tax Rates
- Location: `contracts/virtualPersona/AgentToken.sol` : `setProjectTaxRates`
- Mechanism: The function comment states "Change the tax rates, subject to only ever decreasing", but the code does not enforce this. The owner (or factory) can increase tax rates arbitrarily.
- Impact: The token owner can rug pull by increasing buy/sell taxes to 100% or any high value, effectively preventing trading or stealing tokens during transfer.

## Medium: Genesis Failed State Logic Error
- Location: `contracts/genesis/Genesis.sol` : `onGenesisFailed`
- Mechanism: The function increments `refundUserCountForFailed` only when a participant has a positive `virtualsAmt`. If some participants have zero contributed, they are skipped, and the counter never reaches `participants.length`. The check `if (refundUserCountForFailed == participants.length)` may never be true, leaving the genesis in a non-finalized state.
- Impact: The genesis may never be marked as failed, preventing future actions and leaving the contract in an inconsistent state. Withdrawn assets may also be blocked.

## Low: TBA Lookup Logic Error in promptMulti
- Location: `contracts/AgentInference.sol` : `promptMulti`
- Mechanism: The variable `prevAgentId` is initialized to 0 but never updated inside the loop. The condition `if (prevAgentId != agentId)` will always be true after the first iteration (unless agentId is 0). If the first `agentId` is 0 (unlikely but possible), the TBA lookup is skipped, and `agentTba` remains `address(0)`, causing tokens to be sent to the zero address.
- Impact: Loss of user funds if the first agent ID is 0, or unnecessary gas consumption due to repeated TBA lookups.

## Low: Missing SafeTransferFrom in Migrator
- Location: `contracts/virtualPersona/AgentMigrator.sol` : `migrateAgent`
- Mechanism: The function uses `IERC20(_assetToken).transferFrom(founder, token, initialAmount)` instead of `safeTransferFrom`. If the asset token does not return a boolean (like USDT), or returns false, the transaction will revert or fail silently.
- Impact: Migration will fail for non-standard ERC20 tokens that don't return a bool on transfer.

## Low: Airdrop Total Validation Missing
- Location: `contracts/token/Airdrop.sol` : `airdrop`
- Mechanism: The function takes a `_total` parameter and uses it for the `transferFrom` call, but does not verify that `_total` equals the sum of `_amounts`. The caller could pass a smaller total, and some recipients would not receive tokens (the loop would fail or the contract would have insufficient balance, but the function doesn't check).
- Impact: Airdrop recipients may not receive tokens if the caller provides an incorrect total.

## Low: Missing Zero Address Checks
- Location: `contracts/AgentRewardV2.sol` : `updateRefContracts` and `contracts/AgentRewardV3.sol` : `updateRefContracts`
- Mechanism: These functions allow the admin to set critical addresses (`rewardToken`, `agentNft`, etc.) to `address(0)` without validation. Setting these to zero would break the contract's functionality (e.g., reward claims would fail, or distributeRewards would revert).
- Impact: Admin can accidentally or maliciously brick the reward distribution contract by setting dependencies to the zero address.

## Low: Underflow Risk in getChildrenRewards
- Location: `contracts/AgentRewardV2.sol` : `getChildrenRewards`
- Mechanism: The function calculates `childReward.parentAmount - childReward.totalClaimedParent`. If `totalClaimedParent` exceeds `parentAmount` due to a bug or state inconsistency, this will underflow and revert (in Solidity 0.8).
- Impact: Reward queries for services with children may revert, affecting off-chain consumers and potentially on-chain claim flows.

## Low: Unchecked Return Value in Genesis
- Location: `contracts/genesis/FGenesis.sol` : `createGenesis`
- Mechanism: The function uses `IERC20(params.virtualToken).transferFrom(...)` and checks the return value, but uses the boolean check rather than `safeTransferFrom`. This will fail for tokens that don't return a bool.
- Impact: Genesis creation will fail if the virtual token does not return a bool on transferFrom (e.g., USDT).

## Low: Front-Running Risk in AgentToken distributeTaxTokens
- Location: `contracts/virtualPersona/AgentToken.sol` : `distributeTaxTokens`
- Mechanism: This function is public and transfers accumulated tax tokens to the project tax recipient. An attacker can front-run the call to manipulate the auto-swap or claim the tokens themselves if the recipient is not careful. Additionally, anyone can call this to force distribution, potentially at unfavorable prices.
- Impact: Tax distribution can be front-run or triggered at bad times, but the tokens go to the designated recipient, so impact is limited.

## Low: No Event Emission in Genesis resetTime
- Location: `contracts/genesis/Genesis.sol` : `resetTime`
- Mechanism: The function emits `TimeReset`, but the new start/end times might still be in the past or present, allowing the factory to bypass the `_validateTime` check in `initialize` by resetting after deployment. Wait, the modifier `whenNotStarted` prevents this. But if the genesis is not started, the factory can reset to invalid times (e.g., start in the past). The `_validateTime` requires `startTime > block.timestamp`, so it's safe. But the function can be called multiple times before start.
- Impact: The factory can manipulate the genesis timeline before it starts, but cannot set invalid times.

## Low: Unbounded Loop in AgentRewardV2 getPastRewardSettings
- Location: `contracts/AgentRewardV2.sol` : `getPastRewardSettings`
- Mechanism: Uses binary search with a `sqrt(len)` optimization. This is safe, but the `SafeCast.toUint32(block.number)` could theoretically overflow if block.number > 2^32. In practice, this won't happen for decades, but it's a theoretical issue.
- Impact: Theoretical overflow in the far future.

## Low: Missing Input Validation in AgentTax updateCreator
- Location: `contracts/tax/AgentTax.sol` : `updateCreator`
- Mechanism: The function allows setting the creator to any address, including `address(0)`. Setting to zero would send future tax rewards to the zero address.
- Impact: Tax rewards could be permanently lost if the creator is set to zero.

## Low: Centralization Risks
- Location: Multiple contracts
- Mechanism: The `AgentNftV2.setBlacklist` and `migrateVirtual` functions are controlled by `ADMIN_ROLE`. The `AgentToken` owner can withdraw ETH/ERC20. The `AgentVeToken.setMatureAt` can be changed by the agent NFT admin. The `AgentDAO` can be changed by the current DAO. These are centralization risks where admins can change critical parameters or blacklist agents.
- Impact: Trusted admins can change rules, blacklist agents (preventing staking and rewards), or migrate agent components. This is a centralization risk rather than a direct vulnerability, but it should be documented and governed by a timelock or multisig.
