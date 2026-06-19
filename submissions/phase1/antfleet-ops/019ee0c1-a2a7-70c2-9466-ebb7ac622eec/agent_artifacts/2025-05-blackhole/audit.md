# Audit: 2025-05-blackhole

I found these genuine security issues:

## AVM bribes are paid to the escrow contract instead of the lock owner
- Location: `contracts/Bribes.sol` : `getReward`
- Mechanism: For auto-voted locks, the veNFT owner is the child `AutoVotingEscrow` contract, but `Bribe.getReward()` only checks whether `ownerOf(tokenId) == avm` where `avm` is the manager. It also falls back to an `originalOwner` interface that does not match the current manager flow.
- Impact: Bribe rewards for AVM-managed locks are transferred to the AVM child contract and become stuck, instead of reaching the original user.

## `claim_many` misroutes expired AVM rebase rewards
- Location: `contracts/RewardsDistributor.sol` : `claim_many`
- Mechanism: `claim()` handles AVM-held expired locks by resolving the original owner through `avm.getOriginalOwner()`, but `claim_many()` does not. For expired, non-permanent AVM locks it sends rewards to `ownerOf(tokenId)`, which is the AVM child contract.
- Impact: Batch claims can permanently strand BLACK rewards in AVM child contracts.

## Genesis launch can be blocked or price-skewed by pre-seeding the pair
- Location: `contracts/GenesisPoolManager.sol` : `approveGenesisPool`; `contracts/GenesisPool.sol` : `_addLiquidityAndDistribute`
- Mechanism: The manager checks that the pair balances are zero only when approving the genesis pool. Before `launch()`, anyone can transfer tokens directly to the pair and call `sync()`. Launch later adds liquidity with zero minimum amounts and without rechecking reserves.
- Impact: An attacker can DoS launch with one-sided reserves or force genesis liquidity to be added at an attacker-chosen reserve ratio.

## Late genesis deposits are accepted if epoch transition is delayed
- Location: `contracts/GenesisPool.sol` : `depositToken`; `contracts/GenesisPoolManager.sol` : `depositToken`
- Mechanism: Deposits only check pool status and `block.timestamp >= startTime`; they do not enforce the sale end time or no-deposit window. Those boundaries depend on external epoch-controller calls changing status.
- Impact: If the epoch transition call is delayed, users can deposit after the intended cutoff with last-look information, altering allocations or qualification.

## V3 router entrypoint accepts ETH and does nothing
- Location: `contracts/GlobalRouter.sol` : `exactInput`
- Mechanism: `exactInput()` is external payable but its swap implementation is commented out. It returns the default `amountOut` and never refunds `msg.value`.
- Impact: Users or integrators calling this V3-like entrypoint can permanently lock ETH in the router.

## Governor clock is broken
- Location: `contracts/BlackGovernor.sol` : `clock`, `CLOCK_MODE`
- Mechanism: Both ERC-6372 clock functions return default values. `clock()` returns `0`, so governor state logic that depends on the current clock cannot progress correctly.
- Impact: Proposals can remain stuck or governance timing can be invalid, breaking the only allowed `nudge()` governance path.

## Emissions can become permanently unallocated when total vote weight is zero
- Location: `contracts/GaugeManager.sol` : `notifyRewardAmount`
- Mechanism: The function transfers BLACK from the minter before checking vote weight. If `IVoter(voter).totalWeight()` is zero, `_ratio` remains zero and `index` is not updated, leaving the transferred emissions unclaimable.
- Impact: A zero-weight epoch can strand emissions in `GaugeManager` instead of distributing or returning them.

## Anyone can pollute the CL gauge factory
- Location: `contracts/AlgebraCLVe33/GaugeFactoryCL.sol` : `createGauge`
- Mechanism: `createGauge()` is external and has no access control, even though other administrative functions use `onlyAllowed`. A caller can supply arbitrary pool/farming parameters and append gauges to the factory list.
- Impact: Attackers can create unregistered or malicious gauges, pollute `length()/gauges()`, and break downstream reward enumeration that trusts the factory list.

## Accrued extra rewards can be withdrawn after distribution ends
- Location: `contracts/GaugeExtraRewarder.sol` : `recoverERC20`
- Mechanism: The reward-token protection only applies while `lastDistributedTime > block.timestamp`. After the period ends, accrued-but-unclaimed rewards remain in the contract but the owner can withdraw them all.
- Impact: A malicious or compromised owner can steal users’ pending extra rewards.

## Season reward token can be recovered by the owner
- Location: `contracts/BlackClaims.sol` : `recoverERC20`
- Mechanism: The recovery function has no guard preventing withdrawal of the season reward token, despite the contract holding claimable BLACK balances for users.
- Impact: A malicious or compromised owner can drain funded season rewards before users claim.

## Public mint wallet cap is bypassable
- Location: `contracts/Thenian.sol` : `mintPublic`
- Mechanism: The public-sale cap checks only the caller’s current NFT balance. It does not use `originalMinters` or any cumulative minted counter.
- Impact: A user can mint up to the cap, transfer NFTs away, and mint again, bypassing the 15-NFT-per-wallet limit.

