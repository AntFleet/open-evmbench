# Audit: 2025-04-virtuals

# Open EVMBench Detect Audit Report — Virtuals Protocol (2025-04)

## Contribution NFT mintable before governance approval
- Location: `contracts/contribution/ContributionNft.sol` : `mint`
- Mechanism: `mint` only checks that `msg.sender` is the proposal proposer via `personaDAO.proposalProposer(proposalId)`. It does not require the proposal to exist in a succeeded/executed state (`isAccepted` is never checked). A proposer can therefore mint a Contribution NFT immediately after creating a proposal, while the proposal is still pending or even if it will fail.
- Impact: Attackers can create contribution NFTs for unapproved work, then call downstream functions (e.g. `Minter.mint`) that treat the NFT as legitimate, draining pre-funded agent tokens from the Minter contract and corrupting service/reward accounting.

## Minter distributes tokens without verifying contribution acceptance
- Location: `contracts/token/Minter.sol` : `mint`
- Mechanism: `mint` checks `contribution.isModel(nftId)` and `virtualId != 0`, but never calls `contribution.isAccepted(nftId)` (which verifies DAO proposal state is `Succeeded`). Combined with the ContributionNft flaw above, rewards can be paid for contributions that never passed governance.
- Impact: Anyone can trigger payout of agent tokens from the Minter’s balance for unapproved model contributions, stealing funds intended only for governance-approved contributions.

## AgentToken wallet/transaction limits and bot protection never enforced
- Location: `contracts/virtualPersona/AgentToken.sol` : `initialize`, `_processSupplyParams`, `_beforeTokenTransfer`, `_pretaxValidationAndLimits`
- Mechanism: Factory deployments pass `maxTokensPerWallet`, `maxTokensPerTxn`, and `botProtectionDurationInSeconds` in supply params. `_processSupplyParams` only persists `vault`; the max-wallet and max-txn values are never stored. `botProtectionDurationInSeconds` is stored but never read. `_beforeTokenTransfer` is an empty hook and `_pretaxValidationAndLimits` performs no limit checks.
- Impact: Advertised anti-bot and wallet-cap protections are completely absent. Launch snipers and whales can buy unlimited amounts immediately after liquidity is added, defeating the protocol’s stated tokenomics safeguards.

## Bonding.unwrapToken forcibly burns third-party token balances
- Location: `contracts/fun/Bonding.sol` : `unwrapToken`
- Mechanism: `unwrapToken` is permissionless and accepts an arbitrary `accounts[]` array. For each account with a non-zero balance, it calls `FERC20.burnFrom(acc, balance)` (Bonding is FERC20 owner) and then transfers graduated agent tokens from the pair. No consent, allowance, or ownership check is performed on the listed accounts.
- Impact: Any user can destroy another user’s ungraduated “fun” token balance by including their address in `accounts[]`. If the victim also receives agent tokens, an attacker can grief holders; at minimum this enables unauthorized destruction of user assets.

## Bonding.setFee uses inconsistent fee units
- Location: `contracts/fun/Bonding.sol` : `initialize`, `setFee`
- Mechanism: `initialize` scales the fee as `fee = (fee_ * 1 ether) / 1000`, but `setFee` assigns `fee = newFee` directly with no scaling. After an owner fee update, `launch`/`launchFor` use the raw value in `require(purchaseAmount > fee)` and fee transfers, breaking the intended fee magnitude.
- Impact: Owner fee updates can accidentally set fees to near-zero (undercharging) or far above intended levels (blocking launches and overcharging users), breaking bonding-curve economics.

## FERC20.burnFrom does not reduce totalSupply
- Location: `contracts/fun/FERC20.sol` : `burnFrom`
- Mechanism: `burnFrom` decrements `_balances[user]` and emits a burn event but never decrements `_totalSupply`. Normal `_burn` is not used, so supply accounting becomes permanently inconsistent with balances after any burn.
- Impact: Any on-chain logic or off-chain tooling relying on `totalSupply()` (including market-cap calculations in Bonding metadata) will overstate circulating supply, enabling misleading pricing/analytics and incorrect economic decisions.

## Permissionless validator registration via AgentNft and AgentVeToken
- Location: `contracts/virtualPersona/AgentNftV2.sol` : `addValidator`; `contracts/virtualPersona/AgentVeToken.sol` : `stake`
- Mechanism: `AgentNftV2.addValidator` is public with no access control. Every `AgentVeToken.stake` call also invokes `registry.addValidator(virtualId, delegatee)` for whatever `delegatee` the staker chooses. Validators receive base scores (`_initValidatorScore` sets base to `totalProposals`) and participate in reward weighting.
- Impact: Attackers can inflate the validator set with sybil addresses (including via cheap stakes and arbitrary delegatees), diluting legitimate validator rewards in AgentRewardV2/V3 and manipulating governance-adjacent scoring.

## AgentRewardV3 division-by-zero when no stake or no proposals at distribution
- Location: `contracts/AgentRewardV3.sol` : `_distributeAgentReward`, `getClaimableStakerRewards`, `getClaimableValidatorRewards`, `claimStakerRewards`, `claimValidatorRewards`
- Mechanism: `_distributeAgentReward` records `totalStaked` and `totalProposals` at distribution time without requiring them to be non-zero. Claim/view math divides by `agentReward.totalStaked` and `agentReward.totalProposals`. If either is zero, all claim and view calls revert.
- Impact: Reward epochs created while an agent has zero stake or zero DAO proposals become permanently unclaimable, locking allocated reward tokens in the contract and causing denial-of-service for affected stakers/validators.

## AgentRewardV3 advances claim cursor on zero-value claims
- Location: `contracts/AgentRewardV3.sol` : `claimStakerRewards`, `claimValidatorRewards`, `getClaimableStakerRewards`
- Mechanism: `claimStakerRewards`/`claimValidatorRewards` always set `claim.rewardCount = numRewards` even when `totalClaimable == 0` (e.g., user had no stake at snapshot blocks). The loop bound in `getClaimableStakerRewards` uses `Math.min(LOOP_LIMIT + claim.rewardCount, ...)`, so calling claim with zero entitlement permanently skips those reward indices.
- Impact: Users who claim (or have someone claim on their behalf) before acquiring stake/delegation permanently forfeit past reward epochs they later become eligible for, causing silent loss of rewards.

## AgentRewardV3 LP weighting manipulable via direct token donations
- Location: `contracts/AgentRewardV3.sol` : `getLPValue`, `distributeRewards`
- Mechanism: `getLPValue` uses `IERC20(rewardToken).balanceOf(lp)` on the Uniswap pair address. `distributeRewards` allocates shares proportionally to these balances. Directly transferring reward tokens to a pair address inflates its balance without adding real liquidity.
- Impact: An attacker can donate reward tokens to a chosen agent’s LP address before governance runs `distributeRewards`, skewing allocation toward that agent and extracting a disproportionate share of emissions relative to genuine LP depth.

## AgentRewardV2 staker reward division by zero when delegatee has no votes
- Location: `contracts/AgentRewardV2.sol` : `_getClaimableStakerRewardsAt`
- Mechanism: Staker claimable amount computes `((validatorGroupRewards * tokens) / votes) * stakerShares / DENOMINATOR`, where `votes = getPastVotes(delegatee, mainReward.blockNumber)`. If the delegatee had zero voting weight at the snapshot block, division by zero reverts.
- Impact: Any reward epoch where a staker’s delegatee had zero votes makes claiming staker rewards revert for affected users, locking their share of validator-group rewards.

## AgentDAO.getMaturity division by zero
- Location: `contracts/virtualPersona/AgentDAO.sol` : `getMaturity`
- Mechanism: `getMaturity` returns `Math.min(10000, _proposalMaturities[proposalId] / forVotes)` without checking `forVotes > 0`. If a proposal receives no “For” votes, the division reverts.
- Impact: Service NFT minting and maturity calculations that call `getMaturity` can be bricked for proposals with zero for-votes, blocking service registration and downstream reward/service flows.

## ServiceNft.updateImpact is publicly callable
- Location: `contracts/contribution/ServiceNft.sol` : `updateImpact`
- Mechanism: `updateImpact` has no access control (anyone can call it). It recalculates and overwrites `_impacts` and `_maturities` for a given `proposalId`, affecting reward impact values consumed by AgentRewardV2 and Minter.
- Impact: Attackers can trigger impact recalculations at adversarial times to manipulate service impact scores used in contributor reward splits and Minter payouts, redirecting emissions or reducing legitimate contributors’ shares.

## Airdrop missing array length validation
- Location: `contracts/token/Airdrop.sol` : `airdrop`
- Mechanism: The assembly loop iterates over `_amounts.length` but never requires `_recipients.length == _amounts.length`. It also never verifies `sum(_amounts) == _total`. Mismatched lengths cause out-of-bounds calldata reads; mismatched totals leave excess tokens stuck in the contract with no recovery path.
- Impact: A malformed or malicious airdrop call can transfer tokens to arbitrary addresses parsed from unrelated calldata, or permanently lock surplus tokens in the Airdrop contract.

## AgentFactoryV4 adds entire factory token balance to custom-token LP
- Location: `contracts/virtualPersona/AgentFactoryV4.sol` : `_executeApplication`
- Mechanism: For custom-token applications (`token != address(0)`), `addLiquidity` uses `IERC20(token).balanceOf(address(this))` as the token side rather than the `initialLP` amount deposited in `initFromToken`. Any tokens previously sent to the factory (accidentally or deliberately) are swept into LP.
- Impact: Third parties can force extra tokens into an agent’s initial LP pool, diluting the proposer’s intended ratio and potentially gifting LP value to the proposer/founder at depositors’ expense.

## AgentMigrator allows owner to reset migration flag
- Location: `contracts/virtualPersona/AgentMigrator.sol` : `reset`, `migrateAgent`
- Mechanism: `reset(id)` (owner-only) sets `migratedAgents[id] = false` after a successful migration. A founder can then call `migrateAgent` again for the same virtual ID, deploying a fresh token/DAO/veToken stack while the prior migrated assets still exist.
- Impact: A compromised or malicious owner can duplicate agent infrastructure for the same virtual ID, creating conflicting token/DAO addresses, confusing holders, and enabling double-allocation of migration resources.

## AgentInference checks balance but not allowance before transfer
- Location: `contracts/AgentInference.sol` : `prompt`, `promptMulti`
- Mechanism: Both functions `require(token.balanceOf(sender) >= total)` but never verify allowance before `safeTransferFrom`. This is not directly exploitable (transfers still revert without allowance), but the check gives users a false success precondition and enables griefing patterns where callers with balance but no approval pass the local require and fail later.
- Impact: Low-severity UX/griefing issue; callers can be tricked into failed transactions, and integrators relying on the balance check alone may build incorrect approval flows.

---

**Note:** Findings above are limited to genuine logic, access-control, accounting, and oracle/reward flaws. Style, gas, and purely centralization assumptions about trusted `GOV_ROLE`/`ADMIN_ROLE` holders are omitted unless they enable unprivileged exploitation (e.g., permissionless functions).

