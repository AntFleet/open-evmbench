# Audit: 2025-04-virtuals

## Post-snapshot staking can steal V2 rewards
- Location: `contracts/AgentRewardV2.sol` : `_distributeValidatorRewards`
- Mechanism: `distributeRewards` snapshots `reward.totalStaked`, but later `distributeRewardsForAgents` calculates validator rewards using live `getVotes()` and live validator scores instead of past votes at the reward block.
- Impact: An attacker can stake/delegate after rewards are funded but before agent distribution, receive validator rewards for a period they did not participate in, and even over-allocate rewards beyond the funded amount.

## Arbitrary core IDs over-distribute contributor rewards
- Location: `contracts/contribution/ContributionNft.sol` : `mint`; `contracts/AgentRewardV2.sol` : `_distributeContributorRewards`
- Mechanism: Contribution `coreId` is never validated against the agent’s `coreTypes`. RewardV2 gives one `coreAmount` per distinct service core encountered, even for fake/unregistered cores.
- Impact: A malicious accepted contribution can use extra core IDs to multiply contributor payouts and drain reward funds reserved for other participants.

## Public impact mutation corrupts rewards
- Location: `contracts/contribution/ServiceNft.sol` : `updateImpact`
- Mechanism: Anyone can call `updateImpact` after mint. For current services this can recompute impact against itself and set impact to zero; RewardV2 also caches old `ServiceReward.impact`, so cached nonzero impact can later be divided by a zero or reduced denominator.
- Impact: Attackers can DoS reward distribution, erase competitors’ mint/reward impact, or cause over-crediting of stale service rewards.

## Cross-agent service NFTs can siphon rewards
- Location: `contracts/AgentRewardV2.sol` : `_distributeContributorRewards`
- Mechanism: Rewards are assigned to whatever service NFTs are currently owned by an agent TBA via `getAllServices`; the code never checks that `ContributionNft.tokenVirtualId(serviceId)` matches the rewarded `virtualId`.
- Impact: A service NFT from another agent can be transferred into a target TBA and earn that target agent’s contributor rewards.

## Anyone can bloat validator lists
- Location: `contracts/virtualPersona/AgentNftV2.sol` : `addValidator`
- Mechanism: `addValidator` is public and unrestricted. Reward distribution iterates the full validator list for an agent.
- Impact: An attacker can add many dummy validators and make `_distributeValidatorRewards` run out of gas, blocking rewards for that agent and any batch containing it.

## Staking can hijack another account’s delegate
- Location: `contracts/virtualPersona/AgentVeToken.sol` : `stake`
- Mechanism: `stake(amount, receiver, delegatee)` lets the caller choose any `receiver`, then calls `_delegate(receiver, delegatee)`, which changes the delegate for the receiver’s entire existing veToken balance.
- Impact: An attacker can stake a dust amount to a victim and redirect the victim’s voting power and reward delegate to the attacker.

## LP balance oracle is manipulable
- Location: `contracts/AgentRewardV3.sol` : `getLPValue`, `distributeRewards`
- Mechanism: Agent weighting uses `IERC20(rewardToken).balanceOf(lp)` directly. For AMM pairs, balances can be inflated by direct token transfers without syncing reserves and recovered later with `skim`.
- Impact: An attacker can front-run a reward distribution, temporarily inflate their agent’s LP value, receive an outsized reward share, then recover the manipulation capital.

## Zero proposal or zero stake rewards brick claims
- Location: `contracts/AgentRewardV3.sol` : `getClaimableStakerRewards`, `getClaimableValidatorRewards`
- Mechanism: Claim calculations divide by `agentReward.totalStaked` and `agentReward.totalProposals` without checking for zero.
- Impact: If a reward is created for an agent with zero stake or zero proposals, claims for that reward revert forever and users cannot advance past it.

## Tax distribution can duplicate AgentToken balances
- Location: `contracts/virtualPersona/AgentToken.sol` : `distributeTaxTokens`, `_transfer`, `_autoSwap`
- Mechanism: `_transfer` snapshots `fromBalance` before `_autoSwap`. When `distributeTaxTokens` transfers from `address(this)`, `_autoSwap` can first move contract-held tax tokens to the AMM, then the outer transfer overwrites the contract balance using the stale snapshot.
- Impact: Tax tokens can be duplicated into both the AMM and the tax recipient, inflating balances and corrupting token supply accounting.

## Zero-supply DAOs can execute without votes
- Location: `contracts/virtualPersona/AgentDAO.sol` : `state`, `_tryAutoExecute`
- Mechanism: The DAO treats a proposal as succeeded when `forVotes == getPastTotalSupply(snapshot)`. If total supply is zero, `0 == 0` makes active proposals succeed without any voting power.
- Impact: On zero-threshold or admin-proposed zero-supply DAOs, arbitrary proposals can pass and execute without real voter approval.

## Bonding trades have no slippage protection
- Location: `contracts/fun/Bonding.sol` : `buy`, `sell`
- Mechanism: Public trades accept only `amountIn` and use current reserves for output; callers cannot specify `minOut` or a deadline.
- Impact: Searchers can sandwich buys and sells to force worse execution and extract user value.

## DCA tax swaps use the wrong minimum output
- Location: `contracts/tax/AgentTax.sol` : `dcaSell`
- Mechanism: `minOutput` is computed from `amountToSwap` directly instead of from `router.getAmountsOut`, ignoring price and decimals.
- Impact: Swaps can either fail unnecessarily or execute with far too little slippage protection, allowing MEV to capture tax proceeds.

## Free prompt events and inference inflation
- Location: `contracts/AgentInference.sol` : `prompt`, `promptMulti`
- Mechanism: Zero amounts are accepted. The functions still increment `inferenceCount` and emit `Prompt` events even when no payment is transferred.
- Impact: Attackers can create unpaid prompt events, inflate agent inference counts, and potentially trigger off-chain inference work for free.

## Development tokens and tunnels are unauthenticated
- Location: `contracts/dev/BMWToken.sol` : `mint`; `contracts/dev/BMWTokenChild.sol` : `setFxManager`; `contracts/dev/FxERC20RootTunnel.sol` : `syncWithdraw`; `contracts/dev/FxERC20ChildTunnel.sol` : `syncDeposit`
- Mechanism: Minting, bridge-manager assignment, root withdrawals, and child deposits are callable without real authorization or proof checks.
- Impact: If deployed with value, anyone can mint child tokens or withdraw locked root tokens.

