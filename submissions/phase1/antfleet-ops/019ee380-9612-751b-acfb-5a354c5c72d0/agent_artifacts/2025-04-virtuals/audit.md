# Audit: 2025-04-virtuals

Below are the genuine security vulnerabilities I found. I focused on logic/accounting/access-control flaws with a concrete exploitable path and omitted style/gas observations.

## Missing access control on `ServiceNft.updateImpact` lets anyone zero out a service's impact
- Location: `contracts/contribution/ServiceNft.sol` : `updateImpact`
- Mechanism: `updateImpact(uint256 virtualId, uint256 proposalId)` is declared `public` with no access control. During `mint` it is invoked *before* `_coreServices[virtualId][core] = proposalId` is set, so `prevServiceId` correctly points at the previous core service. After minting, however, `_coreServices[virtualId][core]` equals `proposalId` itself. Any external caller can re-invoke `updateImpact(virtualId, proposalId)`; now `prevServiceId == proposalId`, so `rawImpact = (_maturities[proposalId] > _maturities[proposalId]) ? ... : 0 = 0`, and `_impacts[proposalId]` (and the linked dataset impact) is overwritten with 0.
- Impact: An attacker can permanently zero the recorded impact of any current core service. Because `getImpact` feeds `AgentRewardV2._distributeContributorRewards` and `Minter.mint`, this lets an attacker grief contributors/model-and-dataset owners by erasing the reward weight they earned, redistributing or destroying their share of emissions.

## `AgentRewardV2` validator distribution uses live votes against a stale staked snapshot → over-distribution / insolvency
- Location: `contracts/AgentRewardV2.sol` : `_distributeValidatorRewards` (called from `distributeRewardsForAgents`)
- Mechanism: `reward.totalStaked` is snapshotted in `_prepareAgentsRewards` (at `distributeRewards` time), but the per-validator weight is read with the *current* `IERC5805(stakingAddress).getVotes(validator)` at `distributeRewardsForAgents` time, and `validatorRewards = (amount * votes) / totalStaked`. The two calls are separate transactions (gov first calls `distributeRewards`, later `distributeRewardsForAgents`). Between them, total delegated votes can increase (new staking/delegation), so `Σ validatorRewards` can exceed the allocated `amount`. Each validator’s `participationReward` is stored in `_validatorRewards[validator][rewardId]` and the remainder is added to `validatorPoolRewards`, none of it bounded by `amount`.
- Impact: A validator can stake/delegate additional weight in the window before `distributeRewardsForAgents` to mint themselves a reward entry larger than their fair share, and the aggregate booked rewards can exceed the tokens actually transferred in. Later `_claimValidatorRewards`/`withdrawValidatorPoolRewards` will attempt to pay out more than was funded, draining reward tokens that belong to other agents/epochs until the contract becomes insolvent and honest claims revert.

## `AgentRewardV3` claims divide by `totalProposals`, which is 0 for agents with no DAO proposals → permanent claim DoS
- Location: `contracts/AgentRewardV3.sol` : `getClaimableStakerRewards` / `getClaimableValidatorRewards` (consumed by `claimStakerRewards`, `claimValidatorRewards`, `claimAll*`)
- Mechanism: `_distributeAgentReward` stores `totalProposals = IAgentDAO(dao).proposalCount()` at distribution time. For a freshly graduated agent whose DAO has had no proposals, this is `0`. The claim views then compute `stakerReward = (stakerReward * uptime) / agentReward.totalProposals` (and the analogous validator line). With `totalProposals == 0` this is a division by zero that reverts. Because the claim loop iterates over the whole unclaimed window and any single epoch with `totalProposals == 0` reverts the entire call, the staker/validator can never advance `claim.rewardCount` past it.
- Impact: Rewards distributed to an agent before its DAO ever recorded a proposal are permanently unclaimable for every staker/validator of that agent — funds are locked. (Note `AgentRewardV2` guards the validator side with `totalProposals == 0 ? 0 : ...`, showing the division was known to be hazardous; V3 dropped the guard.)

## `Genesis.onGenesisSuccess` overwrites `claimableAgentTokens` with `=` and can be called repeatedly
- Location: `contracts/genesis/Genesis.sol` : `onGenesisSuccess`
- Mechanism: Distribution amounts are recorded with `claimableAgentTokens[distributeAgentTokenUserAddresses[i]] = distributeAgentTokenUserAmounts[i];` (assignment, not accumulation). The function only gates *token creation* behind `isFirstLaunch`; the refund and distribution bookkeeping run on every call (it is reachable repeatedly by the `FACTORY_ROLE`/operator while `whenNotCancelled whenNotFailed whenEnded` hold). If the same user appears in two distribution batches, or a second `onGenesisSuccess` call is made before the user calls `claimAgentToken`, the earlier `claimableAgentTokens` value is silently clobbered rather than added.
- Impact: A user’s previously-credited but unclaimed agent-token allocation can be erased (or under-credited when listed across batches), causing loss of owed tokens. The agent tokens remain stranded in the Genesis contract, recoverable only by the admin via `withdrawLeftAssetsAfterFinalized`.

## `AgentRewardV2` staker reward loops are unbounded → claim DoS via reward-epoch growth
- Location: `contracts/AgentRewardV2.sol` : `_getClaimableStakerRewards` / `_getClaimableValidatorRewards`
- Mechanism: These iterate `for (uint256 i = claim.rewardCount; i < count; i++)` with no per-call cap, where `count = rewardCount(virtualId)` grows by one each `distributeRewards`/`_prepareAgentsRewards` cycle. `AgentRewardV3` deliberately introduced `LOOP_LIMIT = 100` with `Math.min(...)` to bound exactly this loop, but V2 has no such bound.
- Impact: For an agent that accrues many reward epochs before a staker claims, the unbounded loop can exceed the block gas limit, making `claimAllRewards` (and the view aggregators) permanently revert for that staker — their accumulated rewards become unclaimable. Additionally, `_getClaimableStakerRewardsAt` divides by `votes = getPastVotes(delegatee, blockNumber)`; a delegatee with a recorded delegation but zero historical votes triggers a division-by-zero revert inside the same loop, with the same locking effect.

## `BMWTokenChild.setFxManager` is unauthenticated → unlimited mint/burn
- Location: `contracts/dev/BMWTokenChild.sol` : `setFxManager` (and `mint`/`burn`)
- Mechanism: `setFxManager(address)` has no access control, so any account can set itself as `_fxManager`, after which `mint(user, amount)` and `burn(user, amount)` (gated only by `msg.sender == _fxManager`) let it mint arbitrary tokens to anyone or burn anyone’s balance. (`contracts/dev/BMWToken.mint` and `FxERC20ChildTunnel` are similarly open.)
- Impact: Complete compromise of the token supply. These live under `contracts/dev/` and appear intended as test scaffolding, but if any of them are deployed alongside production they constitute an unlimited-mint backdoor; flagging in case they are not strictly excluded from deployment.

---

Notes on things I checked and judged **not** exploitable: `AgentInference.promptMulti`’s `prevAgentId` is never updated so the TBA cache is simply ineffective (re-fetches each iteration) but always resolves the correct recipient — a gas defect, not a security flaw. The `payable` on `Bonding.buy` is unused but harmless. `veVirtualToken`/`AgentVeToken` reward reads correctly use past-checkpoint lookups, so flash-stake vote manipulation against reward math is not possible in V3.

