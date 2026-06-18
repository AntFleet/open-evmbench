# Audit: 2025-04-virtuals

I analyzed both reports, matched findings by root cause and code path, and merged the one true overlap into a consensus entry. Here is the unified report.

---

# Merged Security Audit Report

This report consolidates two independent audits (Reviewer A — Claude; Reviewer B — Codex) of the same codebase. Findings present in both reports are merged first; findings raised by only one reviewer follow.

## Consensus findings

## AgentRewardV3 reward claims permanently revert on zero snapshot denominators
*(consensus)*
- Location: `contracts/AgentRewardV3.sol` : `getClaimableStakerRewards`, `getClaimableValidatorRewards`, `_distributeAgentReward`
- Mechanism: `_distributeAgentReward` snapshots `totalProposals = IAgentDAO(dao).proposalCount()` and `totalStaked = nft.totalStaked(virtualId)` into the stored `AgentReward` without validating that either is nonzero. The V3 claim functions then divide by these values — `stakerReward = (stakerReward * uptime) / agentReward.totalProposals` and `validatorReward = (validatorReward * uptime) / agentReward.totalProposals`, plus the earlier `/ agentReward.totalStaked` — with no `== 0` guard (unlike V2, which guards `totalProposals == 0 ? 0 : ...`). A freshly created agent DAO has `proposalCount() == 0`, and an agent can have zero staked supply at distribution time.
- Impact: If governance (`GOV_ROLE`) distributes rewards to an agent whose DAO has zero proposals or zero stake, every `getClaimableStakerRewards`/`getClaimableValidatorRewards` and therefore every `claimStakerRewards`/`claimValidatorRewards` call for that agent reverts with division-by-zero. Because `claim.rewardCount` only advances on a successful claim, the bad entry sits inside the loop window permanently — affected users cannot progress their claim cursor past it, and staker and validator rewards for that agent are bricked forever.

## Additional findings (single-reviewer)

## Missing access control on `ServiceNft.updateImpact` lets anyone rewrite service impact
*(Reviewer A only)*
- Location: `contracts/contribution/ServiceNft.sol` : `updateImpact(uint256 virtualId, uint256 proposalId)` (the `public` function, the `_impacts`/`_maturities` write block)
- Mechanism: `updateImpact` is declared `public` with no caller restriction, though it is meant to be invoked only internally from `mint()`. It recomputes `_impacts[proposalId]` (and `_impacts[datasetId]`, `_maturities[datasetId]`) from `_maturities[proposalId] - _maturities[prevServiceId]`, where `prevServiceId = _coreServices[virtualId][core]` is whatever the *current* core service is at call time. Because `_coreServices` shifts every time a newer service is minted, an attacker can call `updateImpact` standalone on an arbitrary existing service NFT and recompute its impact against a different baseline — either zeroing it (calling it on the current core service makes `prevServiceId == proposalId`, so `rawImpact = 0`) or re-inflating an older service whose maturity exceeds the now-current core service.
- Impact: `getImpact()` is read live by `Minter.mint` (token mint amount `= impact * multiplier * 1e18 / DENOM`) and by `AgentRewardV2._distributeContributorRewards` (contributor/service reward weighting). An attacker can zero a competitor's service impact to deny them minted tokens and reward share, or re-inflate their own old service's impact right before a contributor-reward distribution to capture a larger share. No funding or special role is required.

## Missing access control on `AgentNftV2.addValidator` enables permanent reward-distribution DoS
*(Reviewer A only)*
- Location: `contracts/virtualPersona/AgentNftV2.sol` : `addValidator(uint256 virtualId, address validator)` (declared `public`, no modifier); registry in `contracts/virtualPersona/ValidatorRegistry.sol` (`_addValidator` pushes to an unbounded array with no removal path)
- Mechanism: `addValidator` is fully public. It calls `_addValidator`/`_initValidatorScore`, appending to `_validators[virtualId]`, and there is no `removeValidator` anywhere. An attacker can call it in a loop with thousands of fresh, distinct addresses (the `isValidator` guard only blocks exact duplicates) for any `virtualId`. `AgentRewardV2._distributeValidatorRewards` iterates `for (i = 0; i < nft.validatorCount(virtualId); i++)`, and `ValidatorRegistry.totalUptimeScore` does the same.
- Impact: Once the validator array for a target agent is bloated past the block gas limit, `distributeRewardsForAgents` (and any path iterating validators) for that agent reverts with out-of-gas forever — the array cannot be shrunk. This is a permanent, irreversible denial of service on that agent's validator/staker reward distribution, grief-able by any anonymous caller. The junk validators (0 votes) also pollute `validatorPoolRewards` accounting.

## AgentRewardV3 weights cross-agent distribution by manipulable spot LP balance
*(Reviewer A only)*
- Location: `contracts/AgentRewardV3.sol` : `getLPValue(uint256 virtualId)` and its use in `distributeRewards` (`lpValues[i] = getLPValue(virtualIds[i]); ... _distributeAgentReward(virtualId, rewardIndex, (lpValues[i] * balance) / totalLPValues, settings);`)
- Mechanism: `getLPValue` returns `IERC20(rewardToken).balanceOf(lp)` — the live reward-token balance sitting in the agent's pool — and uses it directly as the weight that splits the distributed `balance` across the supplied `virtualIds`. This spot balance is trivially moved by anyone via a swap or a direct donation into a pool.
- Impact: An attacker who observes/front-runs the gov `distributeRewards` transaction can inflate one agent pool's reward-token balance (e.g., a flash-loan-funded buy or a direct transfer) to capture a disproportionate share of that distribution at the other listed agents' expense; the normalization by `totalLPValues` means inflating one pool strictly steals weight from the rest. Using an instantaneous, externally-writable balance as the allocation oracle is the root flaw.

## AgentRewardV2 validator rewards use live `getVotes` against a snapshot `totalStaked`, allowing over-allocation
*(Reviewer A only)*
- Location: `contracts/AgentRewardV2.sol` : `_distributeValidatorRewards` (`uint256 votes = IERC5805(stakingAddress).getVotes(validator); uint256 validatorRewards = (amount * votes) / totalStaked;`)
- Mechanism: `totalStaked` here is `reward.totalStaked`, snapshotted at `_prepareAgentsRewards` (block N, inside `distributeRewards`), but `getVotes(validator)` is read when `distributeRewardsForAgents` runs (a later block M). These are two separate transactions, so stake/delegation can change in between. If tokens are staked/delegated to existing validators between N and M, `Σ getVotes(validator)` can exceed the snapshot `totalStaked`, making `Σ validatorRewards > amount`. The inflated value feeds both per-validator `participationReward` and `validatorPoolRewards += validatorRewards - participationReward`. Claims, by contrast, consistently use `getPastVotes(..., blockNumber)`.
- Impact: Total claimable across stakers, validators, and the validator pool can exceed the reward-token actually funded for that distribution, so later claimants' `safeTransfer` calls revert (the pool is drained by earlier claimants / `withdrawValidatorPoolRewards`). The contract becomes insolvent for that reward epoch. Precondition is a stake/delegation increase between the two governance calls, which is attacker-influenceable by staking right before `distributeRewardsForAgents`.

## Reward-share setters accept unbounded values that brick distribution
*(Reviewer A only)*
- Location: `contracts/AgentRewardV2.sol` : `setRewardSettings(uint16 protocolShares_, uint16 contributorShares_, uint16 stakerShares_, uint16 parentShares_, uint256 stakeThreshold_)`; `contracts/AgentRewardV3.sol` : `setRewardSettings(uint16 protocolShares_, uint16 stakerShares_)`
- Mechanism: Neither setter validates that share values are `<= DENOM` (10000) or that they sum coherently. In `_distributeProtocolRewards`, `protocolShares = (amount * protocolShares) / DENOM`, and `distributeRewards` then computes `balance = amount - protocolAmount` (V3) / `agentShares = amount - protocolShares` (V2). Likewise V3 `_distributeAgentReward` computes `amount - stakerAmount`.
- Impact: A single mis-set value `> 10000` makes `protocolAmount`/`stakerAmount` exceed `amount`, so the subtraction underflows and every `distributeRewards` call reverts — distribution is bricked until the setting is corrected. While gated to `GOV_ROLE`, it is a configuration foot-gun with no on-chain guardrail (the "setter admits invalid values and bricks later logic" class).

## Unrestricted minting in dev/test bridge mocks
*(Reviewer A only)*
- Location: `contracts/dev/BMWTokenChild.sol` : `setFxManager` / `mint` / `burn`; `contracts/dev/BMWToken.sol` : `mint`
- Mechanism: `BMWTokenChild.setFxManager` has no access control, so anyone can become `_fxManager` and then `mint`/`burn` arbitrarily; `BMWToken.mint` is callable by anyone. These are unrestricted minting paths, but the files are explicitly testing/bridge mocks, so they are treated as non-production.
- Impact: If any of these mocks are deployed to production, an arbitrary caller can mint or burn tokens at will. Surfaced for completeness in case any are deployed.

## Airdrop array-length mismatch can read arbitrary calldata as recipients
*(Reviewer B only)*
- Location: `contracts/token/Airdrop.sol` : `airdrop`
- Mechanism: The assembly loop uses `_amounts.length` as the only loop bound and never checks `_recipients.length == _amounts.length`. If `_amounts` is longer than `_recipients`, `calldataload(add(_recipients.offset, offset))` reads calldata beyond the recipients array and interprets unrelated calldata words as recipient addresses. The function also only pulls `_total` from the caller and does not require `_total == sum(_amounts)`, so malformed calldata can drive transfers to unintended decoded addresses as long as the contract has enough token balance.
- Impact: A caller can cause the airdrop contract to transfer tokens to addresses not present in the intended recipient array, potentially draining leftover token balances previously held by the airdrop contract. Preconditions: the airdrop contract holds or receives enough of the target token, and the attacker supplies mismatched arrays or crafted calldata.

## AgentToken supply truncates above uint128 while emitting full amount
*(Reviewer B only)*
- Location: `contracts/virtualPersona/AgentToken.sol` : `_mint`, `_burn`
- Mechanism: `_processSupplyParams` limits `maxSupply` to `type(uint128).max`, but `_mint` accepts a `uint256 amount` and updates `_totalSupply` with `_totalSupply += uint128(amount)` while crediting `_balances[account] += amount` and emitting `Transfer(..., amount)`. `_burn` similarly subtracts `uint128(amount)` from `_totalSupply` while subtracting the full `amount` from the account balance. Any direct or future path that mints or burns an amount above `uint128.max` desynchronizes total supply from balances/events. (Note: Reviewer A examined these casts and judged them bounded by upstream `maxSupply <= type(uint128).max` checks / `SafeCast`; Reviewer B flags the token contract itself as unsafe independent of current factory validation.)
- Impact: If a misconfigured factory or upgrade path passes oversized mint amounts, balances can exceed reported total supply, and burns can destroy balances without reducing total supply by the same amount. Preconditions: an AgentToken is initialized or extended with a mint/burn amount larger than `uint128.max`; current factory validation mitigates normal initialization but the token contract itself does not enforce the bound.

## Bonding tax can exceed 100 percent and break trades
*(Reviewer B only)*
- Location: `contracts/fun/FFactory.sol` : `setTaxParams`; `contracts/fun/FRouter.sol` : `buy`, `sell`
- Mechanism: `setTaxParams` accepts arbitrary `buyTax` and `sellTax` without bounding them to `<= 100`. `FRouter.buy` computes `txFee = fee * amountIn / 100` and then `amount = amountIn - txFee`; `sell` computes `txFee = fee * amountOut / 100` and `amount = amountOut - txFee`. If either tax is set above 100, normal buys or sells revert from underflow.
- Impact: The admin can accidentally or maliciously brick all bonding-curve buys or sells for every pair using the factory. Preconditions: caller has `ADMIN_ROLE` on `FFactory`.

## AgentRewardV2 contributor rewards can divide by zero for agents without core types
*(Reviewer B only)*
- Location: `contracts/AgentRewardV2.sol` : `_distributeContributorRewards`
- Mechanism: `_distributeContributorRewards` reads `coreTypes = nft.virtualInfo(virtualId).coreTypes` and immediately calculates `reward.coreAmount = amount / coreTypes.length` without requiring `coreTypes.length > 0`. Agent core types are mutable through `AgentNftV2.setCoreTypes`, so an agent DAO can set the list empty after creation.
- Impact: Distribution for that agent reverts and the agent reward cannot be populated, blocking contributor/validator accounting for that reward. Preconditions: an agent has an empty `coreTypes` array when `distributeRewardsForAgents` processes it.

## AgentDAO maturity query divides by zero
*(Reviewer B only)*
- Location: `contracts/virtualPersona/AgentDAO.sol` : `getMaturity`
- Mechanism: `getMaturity` calculates `_proposalMaturities[proposalId] / forVotes` without checking that `forVotes > 0`. `ServiceNft.mint` calls `IAgentDAO(info.dao).getMaturity(proposalId)` when minting a service NFT, so proposals with zero for-votes cause downstream service minting to revert.
- Impact: Accepted or otherwise referenced contribution proposals with zero `forVotes` can make service minting impossible for that proposal. Preconditions: a proposal id reaches the service-mint path while its recorded `forVotes` is zero.

---

### Merge notes
- The only finding present in **both** reports is the AgentRewardV3 zero-denominator claim revert (Reviewer A's "claim math divides by `totalProposals`/`totalStaked`" and Reviewer B's "zero snapshot denominators"). They describe the same root cause and code path; I merged them, unioning the locations (Reviewer B additionally cited `_distributeAgentReward` as the snapshot origin) and preserving Reviewer A's specific detail about the `proposalCount()`/`totalStaked` sources, the V2-vs-V3 guard contrast, and the stuck `rewardCount` cursor.
- Reviewer A's "reward-share setters unbounded" (`setRewardSettings`) and Reviewer B's "bonding tax >100%" (`setTaxParams`) are the same *class* of bug (unbounded admin setter bricks later math) but live in different contracts/functions, so they are kept as separate single-reviewer findings rather than merged.
- Reviewer A explicitly examined and dismissed the AgentToken `uint128` truncation that Reviewer B reports; I kept it as a Reviewer B finding and recorded A's dissent inline rather than dropping either position.

