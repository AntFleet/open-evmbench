# Audit: 2025-04-virtuals
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Unrestricted `updateImpact` lets anyone rewrite or zero service/dataset impact scores
*(consensus, 6 of 6 reports)*
- Location: `contracts/contribution/ServiceNft.sol` : `updateImpact(uint256 virtualId, uint256 proposalId)`
- Mechanism: `updateImpact` is `public` with no access control, and `virtualId` is a caller-supplied lookup key never validated against the proposal's true virtual. It overwrites `_impacts[proposalId] = _maturities[proposalId] - _maturities[prevServiceId]` (and the linked dataset's impact/maturity), where `prevServiceId = _coreServices[virtualId][_cores[proposalId]]`. It is meant to run only inside `mint` *before* `_coreServices[...]` is updated to the new service. After mint, an attacker can: (a) re-call `updateImpact(realVirtualId, proposalId)` so `prevServiceId == proposalId`, making `rawImpact = 0` and zeroing the impact; or (b) pass a `virtualId` whose `_coreServices[..][core] == 0`, making `prevServiceId == 0` and `rawImpact = _maturities[proposalId]` — the full maturity instead of the delta vs. the prior core, inflating impact.
- Impact: `getImpact()` feeds `Minter.mint` (`amount = impact * mult * 1e18 / DENOM`, capped only by `maxImpact`; sets `_mintedNfts[nftId]=true` on first call) and `AgentRewardV2._distributeContributorRewards` (uncapped, `impactAmount = coreAmount * impact / _rewardImpacts[...]`). A model/dataset owner can inflate their own impact to capture the maximum mint and almost the entire core reward pool; a pure griefer can zero any contributor's impact, denying rewards and—by front-running `Minter.mint`—permanently giving the owner 0 tokens. Permissionless theft and griefing.

## AgentRewardV3 reward weighting uses a spot, manipulable LP token balance
*(consensus, 6 of 6 reports)*
- Location: `contracts/AgentRewardV3.sol` : `getLPValue(uint256)` and `distributeRewards(uint256,uint256[],bool)`
- Mechanism: `getLPValue` returns `IERC20(rewardToken).balanceOf(lp)` — the instantaneous reward-token (VIRTUAL) reserve of the agent's Uniswap pool — and `distributeRewards` splits the entire pot pro-rata via `(lpValues[i] * balance) / totalLPValues`. There is no TWAP, snapshot, or relationship to staked weight. The spot balance is freely inflatable by a direct token donation or a swap that pushes reward-token into the target pool, then unwound (or recovered via `skim` where supported) after the distribution.
- Impact: Although `distributeRewards` is `onlyGov`, the per-agent weights come from a live AMM/balance reading. An attacker who is a staker/validator of agent X front-runs the predictable governance tx with a (flash-loaned) swap/donation inflating pool X's reward-token balance, capturing a disproportionate share of `balance` and starving co-distributed agents Y, Z. The capital is recoverable, so the only cost is fees/slippage — profitable when the distributed amount is large.

## `AgentNftV2.addValidator` is callable by anyone and grows an unbounded array (reward-distribution DoS)
*(consensus, 4 of 6 reports)*
- Location: `contracts/virtualPersona/AgentNftV2.sol` : `addValidator`
- Mechanism: `addValidator(uint256 virtualId, address validator)` has no access restriction (not gated to DAO/admin/staking contract). Each call pushes to the unbounded `_validators[virtualId]` and seeds `_baseValidatorScore[validator][virtualId]`. Anyone can register arbitrary addresses as validators for any agent.
- Impact: `AgentRewardV2._distributeValidatorRewards` iterates `validatorCount(virtualId)` (and `ValidatorRegistry.totalUptimeScore` loops the full set), making external vote/score reads per validator. An attacker injects thousands of zero-vote validator entries for a target agent so distribution exceeds the block gas limit and permanently reverts — bricking validator/staker reward distribution for that agent. Injected validators earn nothing, so this is unauthenticated, irreversible griefing/DoS.

## AgentRewardV2 validator distribution mixes *current* votes with a *snapshot* stake total
*(consensus, 4 of 6 reports)*
- Location: `contracts/AgentRewardV2.sol` : `_prepareAgentsRewards`, `distributeRewardsForAgents`, `_distributeValidatorRewards`
- Mechanism: `_prepareAgentsRewards` snapshots `mainReward.blockNumber` and `reward.totalStaked`, but `_distributeValidatorRewards` later computes `votes = IERC5805(stakingAddress).getVotes(validator)` (current voting power) and uses current validator scores/proposal counts, then `validatorRewards = (amount * votes) / totalStaked` against the *old* snapshotted denominator. The staker path uses `getPastVotes(..., mainReward.blockNumber)` and V3 uses `getPastVotes` throughout, confirming the intended semantics. Because `distributeRewardsForAgents` is a public gov tx, an attacker can front-run it: stake a large amount and self-delegate (`AgentVeToken.stake` auto-calls `registry.addValidator`) so current `votes` balloon while `totalStaked` stays old.
- Impact: `validatorRewards = amount * hugeVotes / oldTotalStaked` can vastly exceed `amount`, and the new validator's `validatorScore/totalProposals ≈ 1`, so participation reward ≈ that. The attacker then claims via `_getClaimableValidatorRewardsAt` (no votes division), draining `rewardToken` owed to other agents and to `protocolRewards` — reward-pool insolvency and direct theft, gated only on front-running a public gov tx.

## AgentToken `_mint`/`_burn` truncate `totalSupply` to 128 bits while balances/events use the full amount
*(consensus, 3 of 6 reports)*
- Location: `contracts/virtualPersona/AgentToken.sol` : `_processSupplyParams`, `_mint`, `_burn`
- Mechanism: `_balances[account] += amount` and the emitted `Transfer` use the full `uint256 amount`, but `_totalSupply` is updated via `uint128(amount)`. The only guard, `_processSupplyParams`, checks `maxSupply > type(uint128).max` against the *unscaled* supply parameter, whereas the actually-minted amount is `lpSupply * (10 ** decimals())`. A raw supply between ~3.4e20 and 2^128 passes the check, but `raw * 1e18` exceeds 2^128 and `uint128(amount)` silently truncates; `_burn` truncates symmetrically.
- Impact: `totalSupply()` becomes smaller than the summed balances (event/storage desync), corrupting anything keyed off it — notably the autoswap threshold `(_totalSupply * swapThresholdBasisPoints) / BP_DENOM` and external percentage/integrator logic. Precondition: a deployer/factory-admin (or bonding `initialSupply`) configures a scaled supply above 2^128; default ~1e9-token agents (1e27 scaled) do not fire it. Latent integer-truncation/accounting bug where the guard checks the wrong (pre-scaled) quantity.
- Reviewer disagreement: O-shot-1 and O-shot-3 defended this code path as non-truncating, arguing "the `uint128` casts are bounded by the `maxSupply <= type(uint128).max` check"; the flagging reports counter that the check is applied to the pre-scaled value while the scaled `amount` is what truncates.

## Division-by-zero permanently locks rewards / blocks batch claims when `totalProposals == 0` (and `totalStaked == 0`)
*(consensus, 2 of 6 reports)*
- Location: `contracts/AgentRewardV3.sol` : `getClaimableStakerRewards`, `getClaimableValidatorRewards` (seeded by `_distributeAgentReward`)
- Mechanism: `_distributeAgentReward` stores `totalProposals = IAgentDAO(dao).proposalCount()` (and `totalStaked = nft.totalStaked(virtualId)`) at distribution time with no lower bound. For a virtual with zero DAO proposals (or zero stake while its LP still holds reward token so distribution proceeds), the stored value is `0`. Claim views then do `stakerReward = (stakerReward * uptime) / agentReward.totalProposals` (and divide by `totalStaked`), reverting. Because `claim.rewardCount` only advances inside the same claim path, the poisoned index can never be skipped.
- Impact: All staker/validator rewards for that virtual are permanently unclaimable. Worse, the reverting view is reached from `claimAllStakerRewards`/`claimAllValidatorRewards`/`getTotalClaimable...`, so a single poisoned virtual in a user's `virtualIds` list reverts their entire batch claim — DoS across unrelated, otherwise-claimable agents. No attacker action is required beyond a normal distribution to a low-activity agent. (Both reports note the analogous zero-division in `AgentRewardV2._getClaimableStakerRewardsAt` when `getPastVotes(delegatee, ...) == 0`.)

## AgentRewardV3 same-block stake backrun captures rewards from before the stake existed
*(consensus, 2 of 6 reports)*
- Location: `contracts/AgentRewardV3.sol` : `distributeRewards`, `getClaimableStakerRewards`, `getClaimableValidatorRewards`
- Mechanism: `distributeRewards` stores `reward.blockNumber = block.number` and records `agentReward.totalStaked` during that tx. Claims later query `getPastBalanceOf`, `getPastVotes`, and DAO score at that same block number. Checkpoints are block-granular, so a stake/delegation/vote written *later in the same block* is still returned for that block, while `totalStaked` remains the earlier value.
- Impact: A block builder or backrunner stakes/delegates after the distribution tx in the same block and is later counted as if present at the reward snapshot, overclaiming staker/validator rewards. Precondition: same-block ordering opportunity.
- Reviewer disagreement: O-shot-2 acknowledged both reward contracts' snapshots are "sandwich-able around the governance-timed distribution block" but dismissed it as "inherent to single-block snapshot rewards rather than a discrete bug."

## `FERC20` burn paths never decrement `totalSupply`
*(consensus, 2 of 6 reports)*
- Location: `contracts/fun/FERC20.sol` : `_burn`, `burnFrom`
- Mechanism: Both functions decrement `_balances[user]` (and `burnFrom` emits `Transfer(user, address(0), amount)`) but neither decrements `_totalSupply`; `_burn` doesn't even emit a `Transfer`. After the graduation burn `token_.burnFrom(pairAddress, tokenBalance)` in `Bonding._openTradingOnUniswap` and per-account `burnFrom` in unwrap, `totalSupply()` stays permanently inflated.
- Impact: `totalSupply()` overstates circulating supply for the life of the token, so any consumer pricing/rate-limiting off it is wrong — e.g. `_maxTxAmount = (maxTx * _totalSupply) / 100` stays pinned to the original supply, and external integrators/indexers read a value inconsistent with summed balances. No direct drain found (bonding-curve pricing uses pool reserves), so impact is incorrect supply accounting and security-adjacent off-chain logic.

## AgentToken tax rate above 100% mints balances through unchecked underflow
*(consensus, 2 of 6 reports)*
- Location: `contracts/virtualPersona/AgentToken.sol` : `setProjectTaxRates` (and `_processTaxParams`), `_taxProcessing`, `_transfer`
- Mechanism: Tax basis points are stored as `uint16` and never capped to `BP_DENOM` (10000). `_taxProcessing` runs in `unchecked` and subtracts `tax` from the sent amount; if buy/sell tax exceeds 100%, `amountLessTax_ -= tax` underflows to a near-`uint256` value. `_transfer` then debits only the original `amount` from the sender but credits the recipient with the underflowed amount.
- Impact: If a token is initialized or later configured with tax > 100%, any taxed buy/sell inflates the recipient balance massively and corrupts token accounting. Precondition: malicious or erroneous owner/factory tax configuration, after which ordinary traders trigger the mint-like underflow.

## `Airdrop.airdrop` lets anyone sweep leftover token balances
*(consensus, 2 of 6 reports)*
- Location: `contracts/token/Airdrop.sol` : `airdrop`
- Mechanism: The function pulls caller-supplied `_total` from the caller, then transfers each `_amounts[i]` to recipients, but never requires `sum(_amounts) == _total`. Any excess/dust left in the contract from prior calls is mixed with later callers' funds.
- Impact: Any ERC20 tokens accidentally or intentionally left in the `Airdrop` contract can be stolen by an arbitrary caller setting `_total` to zero (or a small value) and listing `_amounts` that transfer the existing balance to themselves; a user can also lose funds by passing `_total` greater than the distributed sum.

## Bonding trades have no user slippage bound
*(consensus, 2 of 6 reports)*
- Location: `contracts/fun/Bonding.sol` : `buy`, `sell`; `contracts/fun/FRouter.sol` : `buy`, `sell`
- Mechanism: Public `buy`/`sell` accept only `amountIn`; the router computes output from current pair reserves at execution time with no `minAmountOut` parameter checked against the user's expectation.
- Impact: Searchers can sandwich buys/sells, moving reserves before the victim trade so the victim buys fewer tokens or sells for fewer asset tokens than expected. Any user submitting public bonding trades is exposed.

## Minority findings

## Genesis per-contributor cap is enforced per call, not cumulatively
*(minority, 1 of 6 reports)*
- Location: `contracts/genesis/Genesis.sol` : `participate(uint256 pointAmt, uint256 virtualsAmt)`
- Mechanism: The cap is checked only against the single-call `virtualsAmt` (`require(virtualsAmt <= maxContributionVirtualAmount, ...)`), while the per-user total accumulates in `mapAddrToVirtuals[msg.sender] += virtualsAmt`. The check never references the running total, so a user can call `participate` repeatedly, each call ≤ cap, to deposit an unbounded cumulative amount.
- Impact: If `maxContributionVirtualAmount` is the intended per-user fair-launch cap (as the name implies), a whale bypasses it by splitting into many calls and monopolizes the genesis allocation.
- Reviewer disagreement: the reporting shot itself hedged that if the cap was truly meant per-transaction, this is benign; no other report addressed it.

## Genesis `participate` emits caller-controlled point amounts
*(minority, 1 of 6 reports)*
- Location: `contracts/genesis/Genesis.sol` : `participate`
- Mechanism: `pointAmt` is accepted from the caller, not derived from the transferred `virtualsAmt`, and is only emitted in the `Participated` event; the contract stores only `virtualsAmt`.
- Impact: A participant can emit arbitrary point values while paying a small token amount. If the operator role or off-chain distribution process consumes the event points, attackers can receive an inflated allocation.
- Reviewer disagreement: the reporting shot hedged that this depends on off-chain consumption of the event; no other report addressed it. (Same function as the cumulative-cap finding above but a distinct root cause, so kept separate.)

## Anyone can hijack a staker's delegation with a dust stake
*(minority, 1 of 6 reports)*
- Location: `contracts/virtualPersona/AgentVeToken.sol` : `stake`
- Mechanism: `stake(amount, receiver, delegatee)` lets the caller choose any `receiver`, then calls `_delegate(receiver, delegatee)`. ERC20Votes delegation applies to the receiver's *whole* voting balance, not just the newly staked amount, with no authorization from `receiver`.
- Impact: On public agents, an attacker stakes a minimal amount for a victim and redirects the victim's entire existing voting power to an attacker-controlled delegatee, affecting DAO votes and validator reward routing.
- Reviewer disagreement: O-shot-3 reviewed `AgentVeToken` stake/mint and concluded there is "no share-inflation surface," but did not address the delegation-authorization path flagged here.

## Tax fallback distribution can double-spend tax tokens
*(minority, 1 of 6 reports)*
- Location: `contracts/virtualPersona/AgentToken.sol` : `distributeTaxTokens`, `_transfer`, `_autoSwap`
- Mechanism: `distributeTaxTokens` calls `_transfer(address(this), projectTaxRecipient, projectDistribution, false)`. `_transfer` caches `fromBalance`, then the nested `_autoSwap` can swap the contract's tax balance before the outer transfer debits it. After the swap, the outer transfer writes `_balances[address(this)] = fromBalance - amount`, ignoring the nested swap's debit.
- Impact: When accumulated tax is above the autoswap threshold, calling `distributeTaxTokens` can route the same tax tokens through the autoswap path *and* transfer them to `projectTaxRecipient`, breaking accounting and inflating effective balances.

## AgentTax DCA slippage is denominated in the wrong token
*(minority, 1 of 6 reports)*
- Location: `contracts/tax/AgentTax.sol` : `dcaSell`
- Mechanism: `dcaSell` computes `minOutput = amountToSwap * (DENOM - slippage) / DENOM`, using the input tax-token amount rather than the router-quoted asset-token output.
- Impact: Slippage protection is denominated against the wrong asset, so it can be far too lax (or cause swaps to fail) depending on price. When too lax, an MEV attacker can sandwich the executor's DCA swap and extract value from agent tax proceeds.

## Custom-token agent execution can be front-run by permissionless pair creation
*(minority, 1 of 6 reports)*
- Location: `contracts/virtualPersona/AgentFactoryV4.sol` : `initFromToken`, `_createPair`, `executeTokenApplication`
- Mechanism: After a custom-token application is created, execution requires `factory.getPair(tokenAddr, assetToken) == address(0)`. Uniswap pair creation is permissionless, so anyone can create the pair before execution.
- Impact: An attacker front-runs `executeTokenApplication` by creating the pair, forcing execution to revert and delaying or preventing that custom-token agent launch until the proposer withdraws and retries (griefing).

## `Virtual` constructor mints initial supply to deployer instead of configured owner
*(minority, 1 of 6 reports)*
- Location: `contracts/token/Virtual.sol` : `constructor`
- Mechanism: The constructor sets ownership to `initialOwner` but mints `_initialSupply` to `msg.sender`, not `initialOwner`. If deployment is performed by a factory/deployer/script on behalf of the intended owner, ownership and initial token custody diverge.
- Impact: The deployer receives the full initial supply even when `initialOwner` is meant to control the token. Precondition: deployment with `msg.sender != initialOwner`.

## Dev bridge token manager can be seized by anyone
*(minority, 1 of 6 reports)* *(conflicting reviews: 1 of 6 reports dismissed this code path)*
- Location: `contracts/dev/BMWTokenChild.sol` : `setFxManager`
- Mechanism: `setFxManager` is public with no access control. The `_fxManager` address gates both `mint` and `burn`, but any caller can replace it with their own address.
- Impact: If this contract is deployed holding value-bearing tokens, any attacker can make themselves the bridge manager and mint arbitrary tokens or burn users' balances.
- Reviewer disagreement: O-shot-3 explicitly excluded `contracts/dev/**` (naming `BMWTokenChild.setFxManager`) as non-production test helpers and did not treat it as a finding.

## `setDatasetImpactWeight` accepts weights > 100%, bricking all future model-service minting
*(minority, 1 of 6 reports)*
- Location: `contracts/contribution/ServiceNft.sol` : `setDatasetImpactWeight(uint16 weight)` (interacting with `updateImpact`)
- Mechanism: `setDatasetImpactWeight` stores `weight` with no upper bound. In `updateImpact`, when a service has a dataset, `_impacts[datasetId] = (rawImpact * datasetImpactWeight) / 10000;` then `_impacts[proposalId] = rawImpact - _impacts[datasetId];`. If `datasetImpactWeight > 10000`, the first term exceeds `rawImpact`, so the subtraction underflows and reverts under checked arithmetic.
- Impact: Once an owner sets `datasetImpactWeight > 10000`, every `ServiceNft.mint` of a model contribution with an associated dataset reverts (mint calls `updateImpact`), bricking the contribution→service pipeline for affected agents until corrected. Values in `[1..10000)` also silently shift the dataset/model reward split. `onlyOwner`, so configuration foot-gun / griefing-by-misconfiguration rather than external exploit.

---

**Reconciliation check:** 44 raw findings across the 6 reports → 20 distinct findings (11 consensus + 9 minority). Report-support counts sum back to 44, so no finding was dropped. The two `Genesis.participate` findings and the two `totalSupply`-truncation findings (`AgentToken` vs `FERC20`) were intentionally kept separate because they differ on root cause or code path.

