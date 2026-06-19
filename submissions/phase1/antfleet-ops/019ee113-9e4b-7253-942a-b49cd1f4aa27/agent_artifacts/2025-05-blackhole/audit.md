# Audit: 2025-05-blackhole

# Security Audit Report

## Bribes.getReward reverts for AVM-owned NFTs due to interface mismatch
- **Location**: `contracts/Bribes.sol` : `getReward()`
- **Mechanism**: The Bribes contract attempts to resolve the original owner for AVM-held veNFTs via `IAutomatedVotingManager(avm).originalOwner(tokenId)`. However, the actual `AutoVotingEscrowManager` contract exposes this function as `getOriginalOwner(uint256)`, not `originalOwner(uint256)`. The function selectors are different (`0x893d20d8` vs `0x5c43a5b8`), so the call reverts. Any veNFT transferred to an AutoVotingEscrow can never have its bribes claimed — `GaugeManager.claimBribes` will revert, leaving accumulated bribe tokens permanently stuck in the Bribe contract.
- **Impact**: Permanent loss of all bribe rewards (external and internal) for every user that enables auto-voting. The owner can only bypass this by `emergencyRecoverERC20`'ing the tokens, effectively stealing user funds.

## BlackGovernor.clock() and CLOCK_MODE() return empty values
- **Location**: `contracts/BlackGovernor.sol` : `clock()`, `CLOCK_MODE()`
- **Mechanism**: Both required overrides are empty bodies. OZ's `Governor` uses `clock()` as the time source for proposal lifecycle checks (`proposalSnapshot`, `proposalDeadline`, quorum lookup, etc.). Returning 0 from `clock()` causes `quorum(proposalSnapshot)` to read the supply at timestamp 0, and `_propose`/`_cancel`/state-machine logic to treat all proposals as either perpetually pending or expired. The governor is effectively inoperable and can be griefed: any user can repeatedly call `propose` because `state()` will never advance, and `cancel` will always succeed.
- **Impact**: Governance is broken. The only path the minter `nudge` flow was designed around is non-functional, so the emission rate can never be properly adjusted by vote, and the minter is stuck with `tailEmissionRate = MAX_BPS` forever (or forced through a defeated proposal path).

## Bribes.recoverERC20AndUpdateData can underflow rewards accounting
- **Location**: `contracts/Bribes.sol` : `recoverERC20AndUpdateData()`
- **Mechanism**: The function subtracts `tokenAmount` from `tokenRewardsPerEpoch[tokenAddress][nextEpochStart]` without checking that the stored value is at least `tokenAmount`. Since Solidity 0.8.13 reverts on underflow, the owner cannot perform an authorized recovery when the per-epoch reward entry is smaller than the requested amount — or worse, the subtraction silently wraps if compiled without the default checked arithmetic, corrupting the reward distribution so that future claimants can over-claim.
- **Impact**: Either a denial-of-service on token recovery, or (if unchecked arithmetic is reintroduced) a future reward over-distribution that drains the bribe pool.

## Bribes.notifyRewardAmount allows unbounded array growth
- **Location**: `contracts/Bribes.sol` : `notifyRewardAmount()`
- **Mechanism**: `notifyRewardAmount` is permissionless and the only check on the reward token is `_isRewardToken`, which returns true for any whitelisted connector. When the token isn't already in `bribeTokens`, it is pushed into the array regardless of the `reward` amount. An attacker can iterate over every connector token with `reward = 0`, bloating `bribeTokens`. Every API caller (`BlackholePairAPIV2._getNextEpochRewards`, `RewardAPI._getNextEpochRewards`, `veNFTAPI._pairReward` external-bribe path) loops over this array and makes external `IERC20.symbol()/decimals()` calls per token.
- **Impact**: Gas-griefing DoS against the off-chain API helpers (out-of-gas revert on view calls) and potential on-chain bloat in any contract that consumes the list.

## Bribes.getReward updates lastEarn before transfer succeeds
- **Location**: `contracts/Bribes.sol` : `getReward()`
- **Mechanism**: `lastEarn[tokens[i]][tokenId] = block.timestamp;` is written before `IERC20(tokens[i]).safeTransfer(_owner, _reward)`. If the reward token is a fee-on-transfer / rebasing / pausable / blacklistable token (e.g., USDC-style with blacklist, or a token whose balance is insufficient due to a prior `emergencyRecoverERC20`), the transfer reverts *after* `lastEarn` is updated. The user's accounting is wiped while the funds remain in the contract, and a retry is impossible because `lastEarn` is already at the current block.
- **Impact**: Honest claimants permanently lose accrued bribe rewards whenever a reward token is non-standard or the contract is drained.

## Inconsistent "next epoch" reward lookup between API contracts
- **Location**: `contracts/APIHelper/BlackholePairAPIV2.sol` and `contracts/APIHelper/RewardAPI.sol` : `_getNextEpochRewards()`
- **Mechanism**: `BlackholePairAPIV2._getNextEpochRewards` queries `tokenRewardsPerEpoch(_token, BlackTimeLibrary.epochStart(block.timestamp))` (current epoch), while `RewardAPI._getNextEpochRewards` queries `IBribeAPI(_bribe).getNextEpochStart()` which returns `BlackTimeLibrary.epochNext(block.timestamp)` (next epoch). The `getPairBribe` / `getExpectedClaimForNextEpoch` views therefore show different reward amounts for the same pool depending on which API is called, with the `BlackholePairAPIV2` version returning rewards that are actively being distributed in the current week, not the upcoming one.
- **Impact**: Front-ends display misleading reward projections, which can cause users to vote on pools expecting future rewards that won't materialize, and to ignore rewards that will.

## MinterUpgradeable.setRewardDistributor accepts zero address
- **Location**: `contracts/MinterUpgradeable.sol` : `setRewardDistributor()`
- **Mechanism**: The function is only gated by `msg.sender == team` and assigns `_rewards_distributor` directly. There is no zero-address check, unlike `setGaugeManager`. If the team mistakenly or maliciously sets this to `address(0)`, the next `update_period()` will revert at `_black.transfer(address(_rewards_distributor), _rebase)`, halting all emissions and locking rebase distribution permanently.
- **Impact**: Permanent halt of the weekly emission cycle; no gauge receives rewards until an upgrade or team intervention.

## GenesisPoolManager.setRouter has inverted zero-check
- **Location**: `contracts/GenesisPoolManager.sol` : `setRouter()`
- **Mechanism**: The body is `require(_router == address(0), "ZA"); router = _router;`. The require demands the *new* router be the zero address, then assigns the new address to storage. The result is the inverse of intent: the owner can only set the router to `address(0)`, bricking all future genesis pool launches.
- **Impact**: Genesis launches are permanently disabled; governance must redeploy or upgrade to recover the parameter.

## veNFTAPIV1.getAllPairRewards length / offset mismatch
- **Location**: `contracts/APIHelper/veNFTAPIV1.sol` : `getAllPairRewards()`
- **Mechanism**: The function computes `length = min(_amounts, totNFTs + avmNFTsOfUser.length)` to size `_lockReward`, but the loop bound is `i < _offset + _amounts` and the in-bounds check is `i >= (totNFTs + avmNFTsOfUser.length)`. When `_amounts > length` (e.g., `_offset + _amounts` exceeds the total available NFTs), the loop iterates past the array bounds of `_lockReward` (writing `i - _offset >= length`) and past the end of `avmNFTsOfUser` (read OOB). In 0.8.13 the write reverts, but the read of `avmNFTsOfUser[avmIndex].id` for an out-of-range `avmIndex` reverts first, causing a DoS for any client that paginates with `_offset > 0` and `_amounts > remaining`.
- **Impact**: API DoS — clients cannot reliably page through NFT rewards.

## CustomPoolDeployer.createCustomPool is callable by anyone
- **Location**: `contracts/CustomPoolDeployer.sol` : `createCustomPool()`
- **Mechanism**: The function lacks any access control modifier and lets any external caller pass arbitrary `creator`, `tokenA`, `tokenB`, and `initialPrice`. It calls `IAlgebraPoolAPIStorage(algebraPoolAPIStorage).setDeployerForPair(customPool)` (the no-arg version) which requires `isCustomDeployer[msg.sender]`. The `msg.sender` here is `CustomPoolDeployer` itself, not the end user, so the call works *only* if the deployer is whitelisted — but the pool creation still succeeds and the user-named `creator` becomes the recorded creator in the Algebra entry point. A malicious user can spam pool creation, wasting gas, polluting the factory's `poolByPair` / `allPairs` enumeration, and potentially griefing off-chain routers that iterate pools.
- **Impact**: Pool spam / factory pollution and griefing of routing APIs that scan `allPairs`.

## CustomPoolDeployer.setAlgebraFeeShare has no upper bound
- **Location**: `contracts/CustomPoolDeployer.sol` : `setAlgebraFeeShare()`
- **Mechanism**: `onlyOwner` setter writes `_newFeeShare` directly to storage with no `require(_newFeeShare <= DENOMINATOR)` or similar bound. The `algebraFeeShare` is later passed to `IAlgebraCommunityVault(vault).proposeAlgebraFeeChange` and `acceptAlgebraFeeChangeProposal`. A malicious or compromised owner can set the share to `type(uint16).max` (65535), causing the community vault to forward the entire fee balance to the configured recipient instead of the intended fractional cut.
- **Impact**: Theft of all LP fees for every pool created via this deployer.

## BlackGovernor.setTeam has no zero-address check
- **Location**: `contracts/BlackGovernor.sol` : `setTeam()`
- **Mechanism**: `require(msg.sender == team, "not team"); team = newTeam;` — no zero check. If `team` is set to the zero address, `setTeam` becomes uncallable (no one is `team`), `acceptTeam` can never be called (no one is `pendingTeam` from a prior call), and `setProposalNumerator` is locked. The team's authority is either bricked or stuck in limbo depending on the previous `pendingTeam` state.
- **Impact**: Permanent loss of the team's ability to tune the proposal threshold.

## BlackGovernor.quorum ignores blockTimestamp argument
- **Location**: `contracts/BlackGovernor.sol` : `quorum()`
- **Mechanism**: The override calls `token.getsmNFTPastTotalSupply()` directly without passing `blockTimestamp`. The intent of a quorum lookup at a proposal snapshot is to use the supply at that snapshot; the implementation uses the current snapshot, which is manipulable by flash-deposits / veNFT creation right before `quorum` is read by the counting logic. Additionally, the function is `view` but `quorum` in OZ Governor is called from the propose/execute path, so the returned value is computed against the *current* total rather than the historical one.
- **Impact**: Quorum is gameable, allowing proposals that should not pass to execute (or vice-versa).

## BlackGovernor.cancel can be called by anyone
- **Location**: `contracts/BlackGovernor.sol` : `cancel()`
- **Mechanism**: The override only checks `state(_proposalId) == ProposalState.Pending` and `proposer == _proposals[_proposalId].proposer`. The second check is meaningless because `proposer` is read from storage and the storage slot for a non-existent proposal is zero. There is no `require(_proposalId != 0 || _proposals[_proposalId].exists)` check, and `_cancel` itself doesn't validate the proposal exists in OZ's Governor. A caller can pass arbitrary target/value/calldata and a bogus `epochTimeHash` to repeatedly invoke `_cancel` with crafted parameters, potentially spending the proposer's bond or, more importantly, polluting the proposal id space.
- **Impact**: Griefing of governance queue and potential state corruption in `_proposals` mapping.

## PermissionsRegistry.removeRole performs wrong swap-and-pop
- **Location**: `contracts/PermissionsRegistry.sol` : `removeRole()`
- **Mechanism**: Inside the per-user cleanup loop, the code does `_addressToRoles[rta[i]][k] = _roles[_roles.length - 1]; _addressToRoles[rta[i]].pop();`. The value being swapped in is taken from the global `_roles` array (which has *just been* mutated to remove the role being deleted) instead of the last element of the user's own roles array. The user's roles list ends up with an arbitrary different role string in the position of the removed role, and the correct last role is lost.
- **Impact**: After removing a role, users retain a phantom unrelated role, causing them to be incorrectly authorized/checked elsewhere (`hasRole` queries would still return false for the removed role, but `addressToRole` view returns garbage).

## Bribes.notifyRewardAmount lacks reward > 0 check (rewardsListLength bloat)
- **Location**: `contracts/Bribes.sol` : `notifyRewardAmount()` (in conjunction with API helpers)
- **Mechanism**: Combined with the permissionless design, this allows an attacker to call `notifyRewardAmount` for every whitelisted connector token with `reward = 0`, growing `bribeTokens` and inflating the iteration in every `getPairBribe` / `getExpectedClaimForNextEpoch` / `getAllPairRewards` view. Each iteration performs an `IERC20(_token).symbol()` and `.decimals()` external call.
- **Impact**: View-function DoS / gas griefing on API consumers.

## AutoVotingEscrow.lockOwner doesn't validate that tokenId belongs to this AVM
- **Location**: `contracts/AVM/AutoVotingEscrow.sol` : `lockOwner()`
- **Mechanism**: The function reads `tokenIdIndex[_tokenId]` and only checks that the index is within `locks.length`. It does not compare against a stored per-AVM salt or maintain a per-AVM mapping keyed by tokenId. The manager only calls it with the correct AVM, so the impact is limited to direct external callers. However, any contract that integrates with the AVM and resolves the AVM address from `tokenIdToAVMId` (a 1-based index) is fine, but a caller that calls `lockOwner` on the wrong AVM (e.g., iterating `avms` for a known tokenId) would receive a *different* user's `owner` address if the arrays happen to align in length.
- **Impact**: Potential owner mis-attribution if the function is exposed to a caller that does not already have the AVM address from `tokenIdToAVMId`. Exploitable in third-party integrations.
