# Audit: 2025-04-virtuals

## Forced delegation of another staker’s voting power
- Location: `contracts/virtualPersona/AgentVeToken.sol` : `stake`
- Mechanism: `stake(amount, receiver, delegatee)` lets the caller choose any `receiver`, then calls `_delegate(receiver, delegatee)` without requiring authorization from `receiver`. An attacker can stake a dust amount of LP tokens to a victim address and set themselves as `delegatee`, overwriting the victim’s existing delegate for the victim’s full veToken balance.
- Impact: An attacker can steal delegated governance power, vote with another user’s stake, and redirect validator rewards tied to those votes.

## Anyone can spam validators and DoS reward distribution
- Location: `contracts/virtualPersona/AgentNftV2.sol` : `addValidator`
- Mechanism: `addValidator` is fully public and does not require the caller to be the DAO, founder, admin, or to have any stake. `AgentRewardV2._distributeValidatorRewards` later iterates over every validator in `validatorCount(virtualId)`. An attacker can add a large number of arbitrary validator addresses to a target agent.
- Impact: Reward distribution for that agent can become permanently too expensive to execute, locking rewards for validators, stakers, and contributors.

## Post-snapshot staking can inflate V2 validator rewards
- Location: `contracts/AgentRewardV2.sol` : `_distributeValidatorRewards`
- Mechanism: `distributeRewards` snapshots `reward.totalStaked`, but actual validator shares are calculated later in `distributeRewardsForAgents` using current `IERC5805(stakingAddress).getVotes(validator)`. A user can wait until after the reward snapshot, stake or force-delegate more voting power before agent distribution, and receive rewards using a denominator from the earlier, smaller stake snapshot.
- Impact: An attacker can receive validator rewards they were not entitled to at the reward snapshot and can cause total validator allocations to exceed the funded reward amount, draining rewards owed to other users.

## Public impact recomputation lets anyone manipulate service rewards
- Location: `contracts/contribution/ServiceNft.sol` : `updateImpact`
- Mechanism: `updateImpact` is public and accepts arbitrary `virtualId` and `proposalId`. It does not verify that the proposal belongs to the virtual, that the caller is the DAO/service owner, or that the service is the correct core service. The function overwrites `_impacts[proposalId]` and dataset impact values used by reward and minting logic.
- Impact: An attacker can inflate their own service impact to receive excessive contributor rewards or token mints, or set a victim service’s impact to zero to deny rewards.

## V3 reward allocation uses manipulable LP token balances
- Location: `contracts/AgentRewardV3.sol` : `getLPValue`, `distributeRewards`
- Mechanism: `getLPValue` uses `IERC20(rewardToken).balanceOf(lp)` as the agent’s LP value. Raw token balances of AMM pairs can be manipulated by direct token transfers without changing reserves; on Uniswap-like pairs, the attacker may later recover excess tokens with `skim`.
- Impact: An attacker can front-run `distributeRewards`, inflate the apparent value of the LP for an agent they control, and redirect a disproportionate share of rewards away from other agents.

## V3 rewards can become permanently unclaimable on zero denominators
- Location: `contracts/AgentRewardV3.sol` : `_distributeAgentReward`, `getClaimableStakerRewards`, `getClaimableValidatorRewards`
- Mechanism: `_distributeAgentReward` stores `totalStaked` and `totalProposals` without checking either is nonzero. Claim calculation later divides by both values. If an agent has LP value but no stake or no DAO proposals at reward creation, every claim touching that reward reverts and the claim cursor cannot advance.
- Impact: Rewards allocated to that agent become permanently locked, and later rewards for the same claimant/agent can also be blocked behind the unclaimable entry.

## Unaccepted contribution NFTs can be minted and used to grief reward claims
- Location: `contracts/contribution/ContributionNft.sol` : `mint`
- Mechanism: `mint` only checks that `msg.sender` is the proposal proposer. It does not require the proposal to have succeeded, does not validate the proposal action, and allows arbitrary `parentId`. A proposer can mint many unaccepted contribution NFTs pointing to a victim parent NFT.
- Impact: Parent reward claiming in `AgentRewardV2._claimServiceRewards` and `getChildrenRewards` can be forced to iterate over attacker-created children, causing gas exhaustion and preventing the parent NFT owner from claiming rewards.

## Bonding trades have no user slippage protection
- Location: `contracts/fun/Bonding.sol` : `buy`, `sell`; `contracts/fun/FRouter.sol` : `buy`, `sell`
- Mechanism: The public buy/sell flow accepts only `amountIn`; users cannot specify `minAmountOut`, max price, or deadline. Output is calculated from reserves at execution time, after any mempool front-running.
- Impact: Attackers can sandwich user trades and force victims to accept arbitrarily worse execution, extracting value from every buy or sell.

## Agent tax DCA slippage bound is calculated in the wrong units
- Location: `contracts/tax/AgentTax.sol` : `dcaSell`
- Mechanism: `dcaSell` computes `minOutput` as `amountToSwap * (DENOM - slippage) / DENOM`, using the input tax-token amount rather than the router’s quoted asset-token output. `_swapForAsset` fetches `amountsOut` but only checks its length and does not use it to enforce slippage.
- Impact: Tax swaps can execute with ineffective price protection, allowing MEV or pool manipulation to extract value from creator and treasury tax proceeds.

## AgentToken tax swaps execute with zero minimum output
- Location: `contracts/virtualPersona/AgentToken.sol` : `_swapTax`
- Mechanism: Automatic tax swaps call `swapExactTokensForTokensSupportingFeeOnTransferTokens` with `amountOutMin = 0`. Any accumulated tax swap can therefore execute at any price.
- Impact: Attackers can sandwich or manipulate the pool around tax swaps and drain value from project tax revenue.

## Genesis success batches overwrite existing user allocations
- Location: `contracts/genesis/Genesis.sol` : `onGenesisSuccess`
- Mechanism: The function is explicitly callable after the first successful launch, but it writes `claimableAgentTokens[user] = amount` instead of adding to the existing claimable balance. A later batch containing the same user overwrites any unclaimed allocation from an earlier batch.
- Impact: A user’s agent-token allocation can be erased or reduced during multi-batch finalization, leaving the overwritten tokens stranded for later withdrawal instead of claimable by the user.

