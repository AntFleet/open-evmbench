# Audit: 2025-05-blackhole

# Open EVMBench Detect Audit — Blackhole (2025-05)

## Bribe rewards sent to AutoVotingEscrow contract instead of depositor
- Location: `Bribe.sol` : `getReward`
- Mechanism: When a veNFT is enrolled in auto-voting, `AutoVotingEscrowManager.enableAutoVoting` transfers the NFT to an `AutoVotingEscrow` instance, so `IVotingEscrow(ve).ownerOf(tokenId)` returns that escrow contract address. `Bribe.getReward` only rewrites the recipient when `_owner == avm`, where `avm` is the manager address read from `IVotingEscrow(ve).avm()` at construction — not the per-token escrow instance that actually owns the NFT. The redirect also calls `IAutomatedVotingManager(avm).originalOwner(tokenId)`, which does not match the `AutoVotingEscrowManager.getOriginalOwner` API used elsewhere.
- Impact: Bribe payouts for auto-voted veNFTs are transferred to the `AutoVotingEscrow` contract (or the call reverts), leaving users unable to claim earned bribes while tokens accumulate in contracts with no withdrawal path.

## `claim_many` omits AVM original-owner routing for expired locks
- Location: `RewardsDistributor.sol` : `claim_many`
- Mechanism: `claim` correctly resolves the beneficiary for expired, non-permanent locks enrolled in the AVM via `avm.getOriginalOwner(_tokenId)`, but `claim_many` always sends directly to `IVotingEscrow.ownerOf(_tokenId)` with no AVM check.
- Impact: Batch claims for expired AVM-managed veNFTs send rebase rewards to the `AutoVotingEscrow` contract instead of the human depositor, effectively locking those funds.

## `setRouter` can only zero the router address
- Location: `GenesisPoolManager.sol` : `setRouter`
- Mechanism: The function uses `require(_router == address(0), "ZA")`, which is the inverse of the intended non-zero validation. The only address that passes is `address(0)`.
- Impact: The owner can accidentally or maliciously set `router` to zero, breaking `GenesisPool.launch` / `_addLiquidityAndDistribute` and permanently preventing genesis pools from completing liquidity deployment.

## Emergency withdraw bypasses genesis maturity lock
- Location: `GaugeV2.sol` : `emergencyWithdraw`, `emergencyWithdrawAmount`
- Mechanism: Normal withdrawals enforce `block.timestamp >= maturityTime[msg.sender]`, but both emergency withdrawal paths omit this check. Genesis liquidity deposited via `depositsForGenesis` sets `maturityTime` for the token owner.
- Impact: Once a gauge owner activates emergency mode, genesis participants (including the token owner) can withdraw staked LP before the configured maturity period, undermining the launch lockup guarantee.

## `emergencyWithdrawAmount` lacks balance validation
- Location: `GaugeV2.sol` : `emergencyWithdrawAmount`
- Mechanism: Unlike `emergencyWithdraw`, which caps withdrawal at `_balanceOf(msg.sender)`, `emergencyWithdrawAmount` accepts an arbitrary `_amount`, decrements `_totalSupply`, and calls `_deductBalance(_amount)` without verifying `_amount <= _balanceOf(msg.sender)`.
- Impact: During emergency mode, a user can attempt withdrawals larger than their stake. Depending on genesis vs. direct gauge balance split, this can cause reverts that grief other withdrawers, or interact badly with `GenesisPool.deductAmount` accounting; it also lets `_totalSupply` diverge from real liabilities if partial paths succeed.

## Concentrated-liquidity gauges created without pool authenticity check
- Location: `GaugeManager.sol` : `_createGauge`
- Mechanism: For `_gaugeType == 0`, the code verifies `IPairFactory(_factory).isPair(_pool)`. For `_gaugeType == 1` (CL), it unconditionally sets `isPair = true` without confirming the address is a legitimate Algebra pool.
- Impact: An attacker can point gauge creation at any contract implementing `token0()` / `token1()` with whitelisted connector tokens, obtain a live gauge and bribes, and potentially attract emissions if the pool is voteable — diluting rewards and enabling governance spam.

## `removeRole` corrupts per-address role mappings
- Location: `PermissionsRegistry.sol` : `removeRole`
- Mechanism: When clearing a removed role from `_addressToRoles[rta[i]]`, the code assigns `_roles[_roles.length - 1]` (a global role name from the roles list) instead of swapping with the last element of that address’s own roles array.
- Impact: After a global role removal, affected addresses retain corrupted `_addressToRoles` entries. Downstream `hasRole` checks can return stale true values or reference invalid roles, breaking access-control assumptions across governance, gauge admin, and genesis manager functions.

## Governor quorum ignores the requested timepoint
- Location: `BlackGovernor.sol` : `quorum`
- Mechanism: `quorum(uint256 blockTimestamp)` accepts a timestamp parameter per the interface but never uses it, always calling `token.getsmNFTPastTotalSupply()` at the current execution context.
- Impact: Quorum for proposals is computed against present smNFT supply rather than the supply at the relevant historical block, allowing quorum manipulation around smNFT mints/burns and producing incorrect pass/fail outcomes.

## `nudge` reads ambiguous global proposal status
- Location: `MinterUpgradeable.sol` : `nudge`
- Mechanism: `nudge` gates weekly `tailEmissionRate` adjustments on `IBlackGovernor(_epochGovernor).status()` with no proposal ID or linkage to `active_period`. It does not verify which proposal’s outcome should apply to the current epoch.
- Impact: Tail emissions can be adjusted based on the wrong proposal state (e.g., an old succeeded/defeated vote unrelated to the current epoch), causing incorrect inflation increases or decreases for an entire weekly mint cycle.

## Silent auction fallback can misprice genesis deposits
- Location: `GenesisPoolManager.sol` : `depositNativeToken`
- Mechanism: If `auctionFactory.auctions(auctionIndex)` returns zero, the code silently substitutes `auctionFactory.auctions(0)` without validating that index 0 matches the intended pricing curve for the pool.
- Impact: A user or governance mistake in `auctionIndex` routes all native/funding conversions through an unrelated auction contract, causing incorrect deposit allocations and unfair genesis pricing.

## `withdraw` in Bribe silently ignores over-withdrawals
- Location: `Bribe.sol` : `withdraw`
- Mechanism: `withdraw` only mutates state when `amount <= balanceOf[tokenId]`; if the voter passes a larger amount, the function returns successfully without reverting or reducing balance.
- Mechanism detail: The voter may believe voting weight was reset when bribe balance was not.
- Impact: Desynchronization between voter accounting and bribe `balanceOf` lets stale bribe balances persist, causing incorrect `earned` calculations and allowing over-claiming or under-claiming of bribe rewards depending on subsequent interactions.

## `setInternalBribe` accepts zero address on gauges
- Location: `GaugeCL.sol` : `setInternalBribe`, `GaugeV2.sol` : `setInternalBribe`
- Mechanism: Both functions use `require(_int >= address(0))` (always true) instead of rejecting the zero address.
- Impact: A compromised or mistaken gauge owner can redirect LP trading fees to `address(0)`, permanently losing fee revenue that should flow to internal bribes.

## `recoverERC20` allows owner to drain reward tokens
- Location: `RewardsDistributor.sol` : `withdrawERC20`
- Mechanism: The owner-only `withdrawERC20` has no restriction preventing withdrawal of the primary `token` used for ve rebase distribution, unlike the comment on `BlackClaims.recoverERC20`.
- Impact: A compromised distributor owner can withdraw all unclaimed rebase rewards, breaking the rebase accounting (`token_last_balance`) and stealing funds owed to veNFT holders.

## Genesis pool `deductAmount` can divide by zero
- Location: `GenesisPool.sol` : `deductAmount`
- Mechanism: `userAmount` is computed as `(totalDeposits * gaugeTokenAmount) / _depositerLiquidity` where `_depositerLiquidity = liquidity / 2`. If `liquidity` is zero (e.g., before launch completes or after edge-case state), division by zero reverts.
- Impact: Gauge withdrawal / emergency flows that call `deductAmount` can be permanently bricked for genesis-linked stakes in certain pool states, locking LP in the gauge.

