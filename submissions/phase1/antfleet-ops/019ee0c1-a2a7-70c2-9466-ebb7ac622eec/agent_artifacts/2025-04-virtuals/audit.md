# Audit: 2025-04-virtuals

## Unbounded Validator Registration DoS
- Location: `contracts/virtualPersona/AgentNftV2.sol` : `addValidator`
- Mechanism: `addValidator` is public and has no access control, stake requirement, or virtual existence validation. Any address can append arbitrary validator addresses to `_validators[virtualId]`. Reward distribution later iterates `validatorCount(virtualId)` in `AgentRewardV2._distributeValidatorRewards`.
- Impact: An attacker can register thousands of bogus validators for an agent and make reward distribution or validator-score reads run out of gas, effectively DoSing rewards for that agent.

## Public Service Impact Recalculation
- Location: `contracts/contribution/ServiceNft.sol` : `updateImpact`
- Mechanism: `updateImpact` is public and accepts an arbitrary `virtualId`. It recomputes `_impacts[proposalId]` using `_coreServices[virtualId][_cores[proposalId]]` without checking that `proposalId` belongs to that virtual agent or that the caller is authorized. Passing a virtual with no previous service makes `prevServiceId == 0`, inflating impact to the full maturity.
- Impact: A model/service owner can inflate service and dataset impact, increasing rewards in `AgentRewardV2` and token payouts in `Minter.mint`.

## RewardV2 Uses Live Votes For Past Rewards
- Location: `contracts/AgentRewardV2.sol` : `_distributeValidatorRewards`
- Mechanism: `distributeRewards` snapshots `mainReward.blockNumber` and `reward.totalStaked`, but `_distributeValidatorRewards` later uses live `getVotes`, live validator set, live validator scores, and live proposal count. If `distributeRewardsForAgents` is called after the main reward is prepared, attackers can stake/delegate before that transaction and withdraw after rewards are assigned.
- Impact: Attackers can capture validator rewards for a reward period they were not staked in, and can over-allocate rewards relative to the recorded `totalStaked`, draining funds meant for legitimate validators/stakers.

## Manipulable LP-Value Reward Oracle
- Location: `contracts/AgentRewardV3.sol` : `getLPValue`, `distributeRewards`
- Mechanism: agent reward weights are based on `IERC20(rewardToken).balanceOf(lp)`. Raw token balances in an AMM pair are manipulable by direct transfers and, for Uniswap-style pairs, recoverable with `skim`. The contract does not use reserves, TWAP, LP supply, or any manipulation-resistant valuation.
- Impact: An attacker can temporarily inflate their agent LP’s reward-token balance before distribution to receive an outsized share of rewards, then recover the donated tokens from the pair.

## Zero-Stake Or Zero-Proposal Rewards Brick Claims
- Location: `contracts/AgentRewardV3.sol` : `getClaimableStakerRewards`, `getClaimableValidatorRewards`
- Mechanism: `_distributeAgentReward` records `totalStaked` and `totalProposals` without requiring either to be nonzero. Claims later divide by `agentReward.totalStaked` and `agentReward.totalProposals`.
- Impact: If a reward is created for an agent with zero stake or zero proposals, all claims for that reward revert. Because claim cursors cannot advance past the reverting reward, later rewards for that account/agent can also become unclaimable.

## Unaccepted Contribution NFTs Can Be Minted
- Location: `contracts/contribution/ContributionNft.sol` : `mint`
- Mechanism: `mint` only checks that `msg.sender` is `proposalProposer(proposalId)`. It does not require the proposal to have succeeded/executed, nor does it verify that the proposal calldata matches the supplied contribution metadata. Downstream contracts trust stored `core`, `parentId`, `isModel`, and `datasetId`.
- Impact: A proposer can create contribution NFTs with arbitrary metadata before approval, then use those records to influence service metadata, parent reward routing, and model/dataset reward accounting if the proposal later executes or is referenced by other contributions.

## Airdrop Can Spend More Than It Pulls
- Location: `contracts/token/Airdrop.sol` : `airdrop`
- Mechanism: the function transfers `_total` from the caller but never verifies that `_total == sum(_amounts)`, and it does not check `_recipients.length == _amounts.length`. The assembly loop transfers every `_amounts[i]` from the contract’s balance.
- Impact: Anyone can drain tokens previously left in the Airdrop contract by calling with `_total` lower than the distributed sum, including `_total == 0` for standard ERC20s that allow zero-value `transferFrom`.

## Bonding Trades Have No Slippage Protection
- Location: `contracts/fun/Bonding.sol` : `buy`, `sell`
- Mechanism: user-facing buys and sells accept only `amountIn`; there is no `minAmountOut`, deadline chosen by the user, or price-bound parameter. The router computes output from current reserves at execution time.
- Impact: Searchers can sandwich users and force trades to execute at a much worse price, extracting value from buyers and sellers on the bonding curve.

## AgentTax DCA Slippage Floor Is Miscomputed
- Location: `contracts/tax/AgentTax.sol` : `dcaSell`
- Mechanism: `dcaSell` computes `minOutput` from the input tax-token amount: `amountToSwap * (DENOM - slippage) / DENOM`. It does not quote expected asset-token output with `router.getAmountsOut`. This assumes a 1:1 price and matching decimals.
- Impact: When the real taxToken/assetToken price differs, the slippage floor is either ineffective or causes unnecessary reverts. Attackers can sandwich DCA swaps and buy the tax tokens at a much worse price than the configured slippage is supposed to allow.

