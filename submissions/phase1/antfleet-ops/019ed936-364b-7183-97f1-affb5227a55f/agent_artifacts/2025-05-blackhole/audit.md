# Audit: 2025-05-blackhole

## Consensus findings

## Genesis pair can be pre-seeded before launch, then launched with zero slippage bounds
*(consensus)*
- Location: `contracts/GenesisPool.sol` : `_addLiquidityAndDistribute` (called from `launch` / `_launchCompletely` / `_launchPartially`); `contracts/Pair.sol` : `mint`; `contracts/RouterV2.sol` : `addLiquidity` / `addLiquidityETH`; `contracts/GenesisPoolManager.sol` : `approveGenesisPool` / `_launchPool`.
- Mechanism: The genesis flow assumes a genesis pair stays uninitialized until `GenesisPool.launch`, but the `genesis` flag (`setGenesisStatus`) is only consulted inside `RouterV2`, never inside `Pair`. `Pair.mint` is external and carries no genesis-status check, so an attacker can transfer both tokens directly to the pair and call `mint` to seed non-zero reserves at an arbitrary price. The RouterV2 guard only blocks `isGenesis(pair) && totalSupply() == 0`, so once any LP exists it no longer applies, and `RouterV2.addLiquidityETH` lacks the genesis guard entirely. `approveGenesisPool` checks `balanceOf(pair) == 0` only at approval time and nothing re-checks emptiness at launch. When `launch` runs, `_addLiquidityAndDistribute` calls `IRouter(_router).addLiquidity(native, funding, stable, allocatedNative, allocatedFunding, 0, 0, address(this), ...)` — `amountAMin`/`amountBMin` are hard-coded to `0` — so `RouterV2._addLiquidity` derives the deposit ratio from the attacker-manipulated reserves and cannot revert.
- Impact: The protocol deposits the entire raised genesis allocation at an attacker-chosen price. The attacker then arbitrages the mispriced pool to extract value from the genesis liquidity (locked/staked on behalf of the token owner and depositors) and holds the manipulated initial LP share. Loss is bounded by the size of the genesis raise. Precondition: the genesis pair is created/approved and the attacker can source both pair assets before the launch epoch (always possible during the open deposit window).

## `RewardsDistributor.claim_many` ignores AVM ownership, stranding rebases for auto-voted locks
*(consensus)*
- Location: `contracts/RewardsDistributor.sol` : `claim_many` (compare with `claim`, which resolves the AVM owner).
- Mechanism: `claim` handles AVM-held expired locks via `if (address(avm) != address(0) && avm.tokenIdToAVMId(_tokenId) != 0) _nftOwner = avm.getOriginalOwner(_tokenId);` before transferring. `claim_many` performs the same expired non-permanent-lock branch but omits the AVM resolution entirely: `address _nftOwner = IVotingEscrow(_voting_escrow).ownerOf(_tokenId); ... IERC20(token).transfer(_nftOwner, amount);`. For an auto-voted lock, `ownerOf` returns the child `AutoVotingEscrow` custody contract, which has no ERC-20 recovery path and cannot move the tokens out.
- Impact: Anyone can call the public `claim_many` on an AVM-enrolled, expired, non-permanent lock and force that lock's accrued rebase to be transferred into the `AutoVotingEscrow` custody contract, where it becomes permanently stuck instead of going to the original owner. Repeatable loss of rebase funds for auto-voting users.

---

## Additional findings (single-reviewer)

## Bribe rewards for auto-voted (AVM-held) NFTs are sent to a contract that cannot recover them
*(Reviewer A only)*
- Location: `contracts/Bribes.sol` : `getReward` (owner resolution `if(_owner == avm) _owner = IAutomatedVotingManager(avm).originalOwner(tokenId);`); interacts with `AutoVotingEscrowManager.sol` (`enableAutoVoting`, `originalOwner`, `setOriginalOwner`) and `AutoVotingEscrow.sol`.
- Mechanism: `AutoVotingEscrowManager.enableAutoVoting` transfers the veNFT to a child `AutoVotingEscrow` contract (`votingEscrow.transferFrom(msg.sender, address(target), tokenId)`), not to the manager. In `Bribe.getReward`, `_owner = IVotingEscrow(ve).ownerOf(tokenId)` therefore returns the child `AutoVotingEscrow` address, while `avm = IVotingEscrow(ve).avm()` is the single manager address. The special-case `if (_owner == avm)` can never be true, so `_owner` stays the child contract and `IERC20(token).safeTransfer(_owner, _reward)` sends the bribe there. The child `AutoVotingEscrow` exposes no ERC-20 transfer/sweep function, so the tokens are permanently locked. Compounding bug: even if the branch were reached, `AutoVotingEscrowManager.originalOwner` is a public mapping that is never written (`setOriginalOwner` is an empty stub), so it would resolve to `address(0)`.
- Impact: Every external-bribe and internal-fee reward owed to a veNFT enrolled in auto-voting is irrecoverably stranded in the `AutoVotingEscrow` contract, even though `GaugeManager.claimBribes` authorizes the original owner to claim. Direct, repeatable loss of user funds for all auto-voting participants.

## Genesis LP can be withdrawn repeatedly without reducing deposit accounting
*(Reviewer B only)*
- Location: `contracts/GaugeV2.sol` : `_withdraw` / `emergencyWithdrawAmount`; `contracts/GenesisPool.sol` : `deductAmount`.
- Mechanism: `GaugeV2._withdraw` lets genesis participants withdraw LP based on `_balanceOf`, then delegates accounting reduction to `GenesisPool.deductAmount`. That function converts LP back to funding-token deposits with floor division: `(totalDeposits * gaugeTokenAmount) / depositerLiquidity`. For a small enough `gaugeTokenAmount` — especially with token decimal mismatches — this rounds to zero, so `userDeposits[account]` is not reduced while the LP is still transferred out.
- Impact: A depositor with any positive genesis balance can repeatedly withdraw small LP amounts whose deposit deduction rounds down to zero, keeping their computed genesis balance unchanged while draining LP from the gauge — stealing LP backing other depositors and the token owner. Precondition: launched genesis pool with LP staked in the gauge and a withdrawal amount that rounds the deposit deduction to zero.

## Public mint wallet cap is bypassable
*(Reviewer B only)*
- Location: `contracts/Thenian.sol` : `mintPublic`.
- Mechanism: `mintPublic` enforces the 15-NFT wallet cap with `balanceOf(msg.sender) + amount <= 15`. Because this checks current holdings rather than cumulative mints, a buyer can transfer minted NFTs to another address and call `mintPublic` again.
- Impact: A user can mint more than the intended per-wallet public-sale cap, up to the collection supply, by cycling NFTs out of the minting wallet. Precondition: public sale is active and the attacker pays the required mint price.

## Silent `uint128` truncation of emission reward in `GaugeCL.notifyRewardAmount`
*(Reviewer A only)*
- Location: `contracts/AlgebraCLVe33/GaugeCL.sol` : `notifyRewardAmount` (`algebraEternalFarming.addRewards(incentivekey, uint128(reward), 0); emit RewardAdded(reward);`); paired `uint128(rewardRate)` cast in `contracts/GaugeManager.sol` : `_distribute`.
- Mechanism: `reward` is a `uint256` and the full amount is pulled via `safeTransferFrom(DISTRIBUTION, address(this), reward)`, but only `uint128(reward)` is forwarded to the Algebra farming (`addRewards`). If `reward > type(uint128).max`, the emitted `RewardAdded(reward)` and the actually approved/forwarded amount diverge and the truncated remainder is stuck in the gauge. The rate returned to `setRates` is likewise re-cast `uint128(rewardRate)`.
- Impact: A real downcast on a value path, but with current BLACK tokenomics (≈5×10²⁶ max supply, weekly emissions ≈10²⁵) the value never approaches 2¹²⁸ (≈3.4×10³⁸), so it is not reachable today. Latent rather than currently exploitable; worth fixing defensively (use the same `uint128` value for transfer, approval, `addRewards`, and the event).

## `GenesisPoolManager.setRouter` has an inverted check that permanently bricks the setter
*(Reviewer A only)*
- Location: `contracts/GenesisPoolManager.sol` : `setRouter`.
- Mechanism: `require(_router == address(0), "ZA"); router = _router;` — the guard is inverted. It only accepts `address(0)`, so the router can never be reset to a valid address; calling it with any real router reverts, and calling it with `address(0)` sets `router` to zero, which then breaks `_launchPool`'s `IGenesisPool(_genesisPool).launch(router, ...)`.
- Impact: Availability/correctness bug: the router used for all genesis launches cannot be migrated, and a single owner call with `address(0)` would brick all future launches. Owner-only, so not directly attacker-exploitable, but a genuine latent footgun in a launch-critical path.

## `TradeHelper.getAmountsIn` always reverts (loop counter underflow)
*(Reviewer A only)*
- Location: `contracts/APIHelper/TradeHelper.sol` : `getAmountsIn`.
- Mechanism: `for (uint i = routes.length-1; i >= 0; i--)` — with an unsigned counter the condition `i >= 0` is always true; when `i == 0` the `i--` underflows, which reverts under Solidity 0.8 checked arithmetic. The function can never complete.
- Impact: The public `getAmountsIn` quoting helper is permanently non-functional; any integrator or UI relying on it for exact-output quoting always reverts. View-only, no funds at risk, but a real correctness bug.

