# Audit: 2025-04-virtuals

An audit of the provided codebase has identified a critical security vulnerability. 

## <Stale `serviceReward.impact` Cache Traps Contributor Payouts>
- Location: `contracts/AgentRewardV2.sol` : `_distributeContributorRewards`
- Mechanism: When distributing contributor rewards to different services under a core type, the contract iterates to accumulate the total current impact into `_rewardImpacts`. For this accumulator, it fetches the *latest* impact dynamically via `serviceNftContract.getImpact(serviceId)`. However, when initializing the local layout tracker (`ServiceReward storage serviceReward`), it caches the service's impact with the condition `if (serviceReward.impact == 0) { serviceReward.impact = impact; }`. Because it guarantees initialization happens only once, this struct value is permanently frozen. 

When subsequently calculating the individual payout amounts, the calculation `impactAmount = (reward.coreAmount * serviceReward.impact) / _rewardImpacts[reward.id][core]` divides the globally growing sum of up-to-date impacts (`_rewardImpacts`) by the specific service's mathematically smaller, permanently stale, and out-of-date subset (`serviceReward.impact`). 
- Impact: If a service's impact rating organically grows over time via `updateImpact()`, the payout loop will systematically undercalculate distributions for that service. A permanent mathematical mismatch emerges where the fractional distributions naturally evaluate to less than 100%, causing significant portions of Agent reward tokens to be irrecoverably stranded and trapped in the `AgentRewardV2` contract forever rather than reaching contributing builders.
