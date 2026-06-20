# Audit: 2025-05-blackhole

## Genesis contributors can bypass the configured post-launch lock and pull LP immediately
- Location: [GaugeV2.sol](/Users/augstar/open-evmbench/audit_sources/2025-05-blackhole/contracts/GaugeV2.sol:221) : `depositsForGenesis` / `_withdraw`
- Mechanism: When a genesis pool launches, `GenesisPool` deposits the entire LP position into the gauge, but `GaugeV2._depositsForGenesis()` only records `maturityTime[_tokenOwner]` and never sets a lock for the other genesis participants. At the same time, `GaugeV2._balanceOf()` includes `IGenesisPool(genesisPool).balanceOf(account)`, so regular contributors are treated as stakers even though their `maturityTime` remains zero. As a result, `GaugeV2._withdraw()` accepts immediate withdrawals from those accounts because `block.timestamp >= maturityTime[msg.sender]` is trivially true. The supporting accounting path is in [GenesisPool.sol](/Users/augstar/open-evmbench/audit_sources/2025-05-blackhole/contracts/GenesisPool.sol:323) `balanceOf` / `deductAmount`.
- Impact: Any genesis contributor can withdraw their share of the LP position immediately after launch, defeating the configured genesis staking maturity and allowing the depositor side of launch liquidity to be drained early.

## `claim_many` permanently misroutes expired AVM rewards to the AVM contract
- Location: [RewardsDistributor.sol](/Users/augstar/open-evmbench/audit_sources/2025-05-blackhole/contracts/RewardsDistributor.sol:219) : `claim_many`
- Mechanism: `claim()` special-cases AVM-managed veNFTs by resolving `avm.getOriginalOwner(_tokenId)` before paying out expired locks, but `claim_many()` omits that branch. For an expired AVM-held lock, `claim_many()` sends the reward to `IVotingEscrow.ownerOf(_tokenId)`, which is the AVM contract itself, not the real user. `AutoVotingEscrow` has no ERC20 recovery path, so once the transfer happens the reward is stranded.
- Impact: Anyone can call `claim_many()` on expired autovoted locks and permanently trap victims’ distributor rewards inside the AVM contract.

## Governance quorum is computed from live SM-NFT supply, so it can be manipulated after voting starts
- Location: [BlackGovernor.sol](/Users/augstar/open-evmbench/audit_sources/2025-05-blackhole/contracts/BlackGovernor.sol:91) : `quorum`
- Mechanism: `BlackGovernor.quorum(uint256)` ignores its `blockTimestamp` input and instead uses `token.getsmNFTPastTotalSupply()`. In [VotingEscrow.sol](/Users/augstar/open-evmbench/audit_sources/2025-05-blackhole/contracts/VotingEscrow.sol:1285), that function returns the current `smNFTBalance`, not a snapshot. Proposal state checks therefore compare cast votes against a quorum that can move during the voting window as users create, grow, or unwind SM-NFT positions.
- Impact: An attacker can change the quorum requirement mid-vote and flip proposal outcomes without changing already-cast votes, making governance results manipulable and non-deterministic.

## CL fee distribution sweeps the Algebra fee share into LP bribes
- Location: [GaugeManager.sol](/Users/augstar/open-evmbench/audit_sources/2025-05-blackhole/contracts/GaugeManager.sol:321) : `_distributeFees`
- Mechanism: For CL pools, `_distributeFees()` withdraws the entire `communityVault` token balances and then calls `GaugeCL.claimFees()`. In [GaugeCL.sol](/Users/augstar/open-evmbench/audit_sources/2025-05-blackhole/contracts/AlgebraCLVe33/GaugeCL.sol:210), `_claimFees()` treats all token balances now sitting on the gauge as distributable fees and forwards them to the internal bribe after only deducting `dibs`. But the same contract’s [getCommunityVaultAccruedFee()](/Users/augstar/open-evmbench/audit_sources/2025-05-blackhole/contracts/AlgebraCLVe33/GaugeCL.sol:293) explicitly subtracts `algebraFee` when computing claimable fees, which shows part of the vault balance is reserved for Algebra rather than LPs.
- Impact: The protocol fee share can be diverted into internal bribes and claimed by voters/LPs instead of reaching the designated Algebra fee recipient.

