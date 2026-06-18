# Audit: 2025-04-virtuals

### 1.  Unauthorized token burning in `Bonding.unwrapToken`
- **Location**: `contracts/fun/Bonding.sol` : `unwrapToken`
- **Mechanism**: The function is public and has no access controls. It takes an arbitrary list of `accounts` and, for each, calls `token.burnFrom(acc, balance)` (which is `onlyOwner` – the Bonding contract itself) and transfers the equivalent agent tokens from the pair to the account. An attacker can pass any set of addresses, causing the burning of other users’ fun tokens without permission.
- **Impact**: An attacker can arbitrarily destroy the fun token holdings of any user, effectively stealing the value of those tokens (the victim receives agent tokens that may be less valuable, but the attacker can also drain the pair’s agent token supply, making future unwrapping impossible). This is a direct theft/denial-of-service of user funds.

---

### 2.  Oracle manipulation via `AgentRewardV3.getLPValue`
- **Location**: `contracts/AgentRewardV3.sol` : `getLPValue` and `distributeRewards`
- **Mechanism**: `getLPValue` reads the current balance of the reward token (`rewardToken`) in the Uniswap V2 pair (`IERC20(rewardToken).balanceOf(lp)`). This balance is used as the weight to split rewards among agents. The balance can be easily manipulated by a flash loan or a large swap, temporarily inflating the reward token reserves of a particular agent’s pool. The `distributeRewards` function (restricted to `GOV_ROLE`) will then allocate a disproportionately large share of rewards to that agent.
- **Impact**: A malicious actor (or a front‑running attacker) can manipulate the LP balance to siphon reward tokens from other agents, stealing protocol rewards.

---

### 3.  Division by zero when claiming rewards for agents with `totalProposals == 0` in `AgentRewardV3`
- **Location**: `contracts/AgentRewardV3.sol` : `getClaimableStakerRewards` and `getClaimableValidatorRewards`
- **Mechanism**: `_distributeAgentReward` stores `IAgentDAO(…).proposalCount()` as `totalProposals` in the `AgentReward` struct. If the DAO has never created a proposal, this value is 0. During reward claims, the code divides by `agentReward.totalProposals` (`stakerReward = (stakerReward * uptime) / agentReward.totalProposals`). The division by zero causes a revert.
- **Impact**: All staker and validator rewards for that agent become permanently unclaimable, freezing user funds.

---

### 4.  Division by zero in `AgentRewardV2._getClaimableStakerRewardsAt` when validator votes are 0
- **Location**: `contracts/AgentRewardV2.sol` : `_getClaimableStakerRewardsAt`
- **Mechanism**: The function computes `((validatorGroupRewards * tokens) / votes)`. If a validator had 0 votes at the snapshot block, `votes` is 0. Even though the reward for that validator would be 0, the division still occurs, causing a revert.
- **Impact**: Any staker who delegated to a validator with 0 votes at the relevant block cannot claim their staker rewards for that reward period, leading to locked funds.

---

### 5.  `claimAllRewards` in `AgentRewardV2` is permanently broken
- **Location**: `contracts/AgentRewardV2.sol` : `claimAllRewards`
- **Mechanism**: The contract uses a custom `noReentrant` modifier that sets a single `locked` boolean. `claimAllRewards` calls `_claimStakerRewards` and `_claimValidatorRewards` sequentially; both functions have the `noReentrant` modifier. The first call sets `locked = true`, and the second call sees `locked` already true and reverts. The entire transaction always fails after the first claim.
- **Impact**: Users cannot batch claim staker and validator rewards in one transaction. The intended all‑in‑one claiming function is unusable, forcing users to make multiple separate calls.

---

### 6.  Division by zero in `AgentRewardV2._distributeContributorRewards` if `coreTypes` is empty
- **Location**: `contracts/AgentRewardV2.sol` : `_distributeContributorRewards`
- **Mechanism**: The line `reward.coreAmount = amount / coreTypes.length` divides by `coreTypes.length`. Although the factory enforces `coreTypes.length > 0`, a future upgrade or a bug could allow an agent to be created with an empty coreTypes array. If that happens, the division reverts during reward distribution.
- **Impact**: Reward distribution for that agent (and potentially the whole protocol if the loop is in `_prepareAgentsRewards`) would be blocked, causing a denial of service.
