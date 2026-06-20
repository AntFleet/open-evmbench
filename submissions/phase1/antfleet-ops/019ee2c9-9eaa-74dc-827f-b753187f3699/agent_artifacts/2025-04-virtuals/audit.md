# Audit: 2025-04-virtuals

## Anyone can rewrite service impact and steal contributor economics
- Location: `contracts/contribution/ServiceNft.sol` : `updateImpact`
- Mechanism: `updateImpact` is `public` and has no access control, but it mutates `_impacts` and `_maturities` that downstream reward logic trusts. After a model service is minted, `_coreServices[virtualId][core]` points at that same `proposalId`, so a later external call to `updateImpact(virtualId, proposalId)` makes `prevServiceId == proposalId` and forces `rawImpact = 0`. More generally, any caller can recompute a service against a different baseline and arbitrarily deflate or re-shape impact values.
- Impact: An attacker can zero out a competitor's service impact before `AgentRewardV2` distribution or before `Minter.mint`, denying them contributor rewards and token emissions, or manipulate relative impacts to shift a larger share of rewards toward their own contribution.

## Public validator registration lets anyone siphon validator rewards
- Location: `contracts/virtualPersona/AgentNftV2.sol` : `addValidator`
- Mechanism: `addValidator` is unrestricted. When it adds a new validator, `ValidatorRegistry._initValidatorScore` seeds that address with `_getMaxScore(virtualId)`, which is the current `totalProposals`. `AgentRewardV2._distributeValidatorRewards` then treats `validatorScore / totalProposals` as the participation multiplier, so a freshly-added validator starts with full participation credit despite never voting historically.
- Impact: Any attacker can register themself as a validator on any public agent, stake/delegate votes to themself, and collect validator rewards reserved for legitimate validators. The same public entrypoint also lets an attacker bloat the validator array until reward distribution runs out of gas.

## Reward V2 mixes a stake snapshot with live votes, enabling over-allocation
- Location: `contracts/AgentRewardV2.sol` : `distributeRewards`, `distributeRewardsForAgents`, `_distributeValidatorRewards`
- Mechanism: `distributeRewards` snapshots `reward.totalStaked` during `_prepareAgentsRewards`, but actual validator rewards are computed later in `_distributeValidatorRewards` from live `getVotes(validator)`. Because those happen in separate transactions, stake and delegation can be increased after the snapshot but before `distributeRewardsForAgents`, so summed live votes can exceed the snapshotted `totalStaked`.
- Impact: An attacker can stake/delegate in that gap and make total validator/staker claims exceed the reward amount actually funded for the epoch. The contract then becomes insolvent for that reward round, so later claimants or pool withdrawals revert.

## Reward V3 can permanently brick claims on zero-denominator snapshots
- Location: `contracts/AgentRewardV3.sol` : `_distributeAgentReward`, `getClaimableStakerRewards`, `getClaimableValidatorRewards`
- Mechanism: `_distributeAgentReward` stores `totalProposals` and `totalStaked` without validating they are nonzero. The claim paths later divide by both values with no guard. If rewards are created for an agent with zero proposals or zero stake, every claim calculation for that reward entry reverts.
- Impact: A single bad reward entry permanently blocks all future staker and validator claims for that agent, because the user's `rewardCount` cursor never advances past the reverting item.

## Reward V3 uses manipulable LP spot balances as its allocation oracle
- Location: `contracts/AgentRewardV3.sol` : `getLPValue`, `distributeRewards`
- Mechanism: Cross-agent reward splitting is based on `IERC20(rewardToken).balanceOf(lp)` at distribution time. That balance is an instantaneous, externally writable spot value: anyone can change it with a swap or direct token transfer right before governance calls `distributeRewards`.
- Impact: An attacker can front-run a distribution, temporarily inflate their target agent's LP balance, and divert a disproportionate share of the shared reward pool away from other agents.

## Bonding trades are fully sandwichable because users cannot set slippage bounds
- Location: `contracts/fun/Bonding.sol` : `buy`, `sell`
- Mechanism: The public trade functions accept only `amountIn` and `tokenAddress`; they expose no `minOut`/`maxIn` constraint to the caller. Execution always uses whatever reserves exist when the transaction lands, so a front-run price move does not invalidate the trade.
- Impact: MEV bots can sandwich buys and sells, forcing users to trade at manipulated prices and extracting value from every unprotected transaction.

