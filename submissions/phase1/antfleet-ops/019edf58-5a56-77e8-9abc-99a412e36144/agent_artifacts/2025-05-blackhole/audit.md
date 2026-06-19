# Audit: 2025-05-blackhole

# Smart Contract Security Audit Report

## Bonus reward token shadowed to zero address
- Location: `GaugeManager.sol` : `_createGauge`
- Mechanism: The function declares `address bonusRewardToken = bonusRewardToken;`, which shadows the function parameter with a new local variable. In Solidity, the right-hand side resolves to the newly declared (uninitialized) variable, so `bonusRewardToken` is always set to `address(0)`. This value is then passed to `IGaugeFactoryCL.createGauge(..., bonusRewardToken)` for every CL gauge, regardless of what the caller supplied to `createGaugeWithBonusReward`.
- Impact: All concentrated-liquidity gauges are created with `bonusRewardToken = address(0)`. Any intended bonus-reward functionality on CL gauges is silently broken; bonus rewards can never be distributed.

## Owner can drain unclaimed user rewards via recoverERC20
- Location: `BlackClaims.sol` : `recoverERC20`
- Mechanism: The NatSpec states "Cannot be called to withdraw emissions tokens," but the implementation has no check preventing recovery of the rewards token (`token`). `onlyOwner` is satisfied by either `owner` or `secondOwner`, and the function transfers the *entire* balance of any token (including the season reward token) to the caller. After a season is finalized, reward tokens are held in the contract pending user claims; this function can sweep them.
- Impact: Either owner can steal all unclaimed season rewards belonging to users, at any time, simply by calling `recoverERC20(address(token))`.

## claim_many does not route expired-lock rebase to AVM original owner
- Location: `RewardsDistributor.sol` : `claim_many`
- Mechanism: When a lock has expired and is not permanent, `claim` correctly checks whether the NFT is held by the AVM and, if so, sends the rebase tokens to `avm.getOriginalOwner(_tokenId)`. `claim_many` omits this check and sends directly to `IVotingEscrow(_voting_escrow).ownerOf(_tokenId)`, which is the AVM contract address when the NFT is auto-voting.
- Impact: Rebase rewards for expired locks of AVM-deposited NFTs, when claimed via `claim_many`, are transferred to the `AutoVotingEscrow` contract which has no function to retrieve them — funds are permanently stuck.

## RewardsDistributor owner can withdraw all reward tokens
- Location: `RewardsDistributor.sol` : `withdrawERC20`
- Mechanism: `withdrawERC20` transfers the full balance of any token (including the rebase reward token) to `owner`, with no restriction against the reward token and no relation to unclaimed amounts. Pending rebase tokens for all veNFT holders are held in this contract.
- Impact: Owner can drain the entire rebase pool, preventing all future `claim`/`claim_many` calls from paying users their accrued rewards.

## getAmountsIn always reverts (DoS)
- Location: `TradeHelper.sol` : `getAmountsIn`
- Mechanism: The loop `for (uint i = routes.length-1; i >= 0; i--)` uses an unsigned index with `i >= 0` (always true) and decrements `i`. When `i == 0`, the body executes, then `i--` underflows. In Solidity 0.8 this triggers an overflow revert, aborting the entire transaction after computing `amounts[0]` but before returning.
- Impact: `getAmountsIn` is completely unusable — every call reverts. Any consumer relying on it for "amount in" quotes for multi-hop routes is broken.

## setRouter is uncallable (zero-address requirement inverted)
- Location: `GenesisPoolManager.sol` : `setRouter`
- Mechanism: The function asserts `require(_router == address(0), "ZA");`, the opposite of the intended zero-address guard. Since `onlyOwner` is also present, the only call that can succeed is one passing `address(0)`, which would brick pool launches.
- Impact: The router cannot ever be updated to a valid address through this function; governance is unable to change routers post-deployment.

## removeRole corrupts per-address role mappings
- Location: `PermissionsRegistry.sol` : `removeRole`
- Mechanism: When cleaning up `_addressToRoles[rta[i]]` for each address that had the removed role, the swap-and-pop assigns `_roles[_roles.length - 1]` (a role from the *global* roles array, which itself was just mutated by the earlier `_roles.pop()`) into the slot being removed, then pops. It should instead use `_addressToRoles[rta[i]][__roles.length - 1]`. The result is that each affected address's role list is corrupted: a random role label is inserted and a real entry is lost.
- Impact: `addressToRole` returns incorrect data for any address that held the removed role, breaking off-chain role introspection and any on-chain consumer of `addressToRole`.

## setInternalBribe accepts zero address (broken guard)
- Location: `GaugeCL.sol` : `setInternalBribe`
- Mechanism: The validation is `require(_int >= address(0), "zero");`. Since every address is `>= address(0)`, this guard is a no-op. An owner (or `GaugeFactoryCL.setInternalBribe` batch caller) can set `internal_bribe = address(0)`.
- Impact: Once `internal_bribe` is zero, `_claimFees` will attempt `IBribe(address(0)).notifyRewardAmount(...)` which reverts (no code at address 0), permanently blocking fee distribution from that gauge until re-set.

## Clock returns zero in Governor (potential voting breakage)
- Location: `BlackGovernor.sol` : `clock` / `CLOCK_MODE`
- Mechanism: `clock()` is overridden to return `uint48(0)` (empty body) and `CLOCK_MODE()` returns `""`. OpenZeppelin Governor internals use `clock()` to determine the timepoint for voting-power snapshots and proposal state transitions.
- Impact: Snapshot/vote accounting that depends on `clock()` will operate against timepoint 0, potentially causing proposals to be stuck, votes miscounted, or `state()`/quorum checks to behave incorrectly. (Full impact depends on the `L2Governor` base, but an always-zero clock is a clear defect in a governance-critical function.)
