# Audit: 2023-12-ethereumcreditguild

## LendingTermOffboarding lacks required Core roles  
- **Location:** `src/governance/LendingTermOffboarding.sol` : `offboard()` / `cleanup()`  
- **Mechanism:** `offboard()` calls `GuildToken.removeGauge(term)` (requires `GAUGE_REMOVE`), `SimplePSM.setRedemptionsPaused(true)` (requires `GOVERNOR`), and `cleanup()` calls `core().revokeRole(...)` (requires the `GOVERNOR` admin role for those roles) and `SimplePSM.setRedemptionsPaused(false)` (requires `GOVERNOR`). The offboarding contract itself is never shown to hold any of these roles, and it should not need the omnipotent `GOVERNOR` role.  
- **Impact:** `offboard()` and `cleanup()` revert, so the offboarding mechanism is unusable through this contract.

## SurplusGuildMinter cannot unstake due to wrong access control on surplus withdrawal  
- **Location:** `src/loan/SurplusGuildMinter.sol` : `unstake()`  
- **Mechanism:** `unstake()` repays the user by calling `ProfitManager(...).withdrawFromTermSurplusBuffer(term, msg.sender, amount)`, which is protected by `onlyCoreRole(CoreRoles.GUILD_SURPLUS_BUFFER_WITHDRAW)`. `SurplusGuildMinter` is not given that role, so the withdrawal reverts. The asymmetry with `stake()` (which uses the unprivileged `donateToTermSurplusBuffer`) means users can deposit but cannot withdraw.  
- **Impact:** All user funds staked through `SurplusGuildMinter` are locked; the unstake path is permanently broken.

## `SurplusGuildMinter.getRewards()` slashes every user after any gauge loss due to reading stale user stake  
- **Location:** `src/loan/SurplusGuildMinter.sol` : `getRewards()`  
- **Mechanism:** The function declares `UserStake memory userStake;` and then evaluates `lastGaugeLoss > uint256(userStake.lastGaugeLoss)` before assigning `userStake = _stakes[user][term];`. Because the memory struct is initially zero, this comparison becomes `lastGaugeLoss > 0`, returning `slashed = true` for any term that has ever had a loss, regardless of the actual user’s `lastGaugeLoss`.  
- **Impact:** After the first loss in a term, every call to `getRewards()` (including via `stake()` and `unstake()`) treats every user as slashed, zeroes their stake, and prevents legitimate unstaking/reward claims.

## `ProfitManager.notifyPnL()` does not restrict `gauge` to the calling term  
- **Location:** `src/governance/ProfitManager.sol` : `notifyPnL()`  
- **Mechanism:** The function only checks that `msg.sender` holds `GAUGE_PNL_NOTIFIER_ROLE`. It never enforces that the `gauge` argument equals `msg.sender`. Since all lending terms share the same role, any term (or a compromised term) can report profit or loss for any other gauge.  
- **Impact:** A malicious or buggy lending term can trigger unjustified gauge losses on other terms or unfairly redirect profit accounting.

## Stale offboarding polls can be reused after a term is re-onboarded  
- **Location:** `src/governance/LendingTermOffboarding.sol` : `supportOffboard()` / `proposeOffboard()`  
- **Mechanism:** Polls are keyed only by `(snapshotBlock, term)` and stay active for `POLL_DURATION_BLOCKS`. There is no invalidation when a term is offboarded, cleaned up, and later re-onboarded. `proposeOffboard()` merely prevents concurrent new polls via `lastPollBlock`, but it does not clear old active polls.  
- **Impact:** Votes cast in a previous offboarding attempt can be mobilized again to immediately offboard a term that has been re-onboarded, bypassing the need for a fresh poll and the `lastPollBlock` delay.

## Entering rebasing reverts when no accounts are currently rebasing  
- **Location:** `src/tokens/ERC20RebaseDistributor.sol` : `_enterRebase()` → `updateTotalRebasingShares()`  
- **Mechanism:** `updateTotalRebasingShares` handles an increase in shares by computing `percentChange = (sharesAfter * START_REBASING_SHARE_PRICE) / sharesBefore`. If no account is rebasing, `sharesBefore == 0`, causing a division by zero. This happens on the very first `enterRebase()` unless a rebasing balance has already been seeded, and it happens again if all accounts ever exit rebase.  
- **Impact:** If the rebasing supply ever reaches zero, the rebasing feature becomes permanently unavailable; no new account can enter rebase.

## `DeployProposal` defaults to a publicly known private key  
- **Location:** `scripts/DeployProposal.s.sol` : `_parseEnv()` / `run()`  
- **Mechanism:** `PRIVATE_KEY` defaults to the well-known Anvil test account 0 private key via `vm.envOr("ETH_PRIVATE_KEY", 0x...)`. If the script is executed without overriding `ETH_PRIVATE_KEY`, all on-chain actions are signed with a key that is public.  
- **Impact:** An attacker or anyone with access to the deployment context can derive the deployer address and/or replay/subsume the deployment, giving them the initial `GOVERNOR` role.
