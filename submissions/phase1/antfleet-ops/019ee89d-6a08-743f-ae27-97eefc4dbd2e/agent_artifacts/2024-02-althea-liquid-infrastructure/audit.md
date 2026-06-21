# Audit: 2024-02-althea-liquid-infrastructure

## Duplicate holder entries cause repeated distribution payouts
- Location: LiquidInfrastructureERC20.sol : `_beforeTokenTransfer` (exploited through `distribute`)
- Mechanism: `_beforeTokenTransfer` appends `to` to the `holders` array whenever `this.balanceOf(to) == 0`, with no check that `to` is already present. The hook runs before balances are updated and ERC-20 permits zero-value transfers, so an attacker can call `transfer(addr, 0)` against any approved address whose balance is currently 0 to push it onto `holders`, repeat it K times, then send it real tokens (its balance is still 0 at the next before-hook, so it is pushed once more). `distribute` then iterates `holders` by index and pays `erc20EntitlementPerUnit[j] * balanceOf(recipient)` for every occurrence, so a duplicated address collects its full entitlement once per duplicate (its `balanceOf` is unchanged because payouts are made in the *distributable* tokens, not the share token).
- Impact: An attacker can register one funded address many times and drain the distributable ERC-20 pool, stealing the rewards owed to all other holders.

## Distribution can be permanently bricked by a reverting distributable token, freezing mint/burn
- Location: LiquidInfrastructureERC20.sol : `distribute` / `_beginDistribution` / `_endDistribution`
- Mechanism: `distribute` pays each distributable token via `if (toDistribute.transfer(recipient, entitlement))`. A token that *reverts* instead of returning false on a given transfer — e.g. USDC/USDT blacklisting a holder or the contract, or a holder contract that reverts — reverts the whole call at that index, so `nextDistributionRecipient` never advances and the distribution can never reach `_endDistribution`. Since `LastDistribution` is only updated by a fully-completed `_endDistribution`, `_isPastMinDistributionPeriod()` stays true forever, and `_beforeMintOrBurn` then blocks every mint and burn.
- Impact: A single blacklisted or hostile holder permanently halts all distributions (rewards become unclaimable) and freezes minting/burning for everyone, recoverable only if the owner manually disapproves the offending holder.

## Unbounded `holders` growth via permissionless zero-value transfers (gas DoS)
- Location: LiquidInfrastructureERC20.sol : `_beforeTokenTransfer` / `_afterTokenTransfer` / `distributeToAllHolders`
- Mechanism: `_beforeTokenTransfer` only checks `isApprovedHolder(to)` (not the sender) and pushes a new `holders` entry for any zero-balance `to`, with no `amount > 0` guard and no dedup. Anyone can therefore spam `transfer(approvedEmptyAddress, 0)` to append entries without limit. `_afterTokenTransfer` performs an unbounded O(n) linear scan of `holders` on every balance-zeroing transfer, and `distributeToAllHolders()` (and a large `distribute`) iterate the whole array in one transaction.
- Impact: An attacker can inflate `holders` until ordinary transfers and full distributions exceed the block gas limit, denying distributions and making transfers prohibitively expensive for all users.

## Incomplete holder removal in `_afterTokenTransfer`
- Location: LiquidInfrastructureERC20.sol : `_afterTokenTransfer`
- Mechanism: When a balance reaches 0 the loop swaps the last element into index `i`, pops, then continues with `i++` and has no `break`. The element just moved into slot `i` is never re-examined, so if `from` appears more than once (see the duplicate-insertion flaw) only one copy is removed, and a distinct holder swapped into the current slot is skipped during the same scan.
- Impact: The `holders` set is corrupted — fully-divested or duplicated addresses linger in the array and continue to receive distributions, compounding the over-distribution accounting error.

## Front-running `distribute()` to capture a full period's rewards
- Location: LiquidInfrastructureERC20.sol : `distribute` / `_beginDistribution`
- Mechanism: Rewards accrue into the contract over `MinDistributionPeriod` (harvested by `withdrawFromManagedNFTs`), but `_beginDistribution` snapshots entitlement as `balance / totalSupply` and `distribute` pays purely on `balanceOf(recipient)` at distribution time with no time-weighting. `distribute` is permissionless, so an approved account can acquire a large balance from another approved holder and call `distribute` in the same block, capturing rewards it never helped earn.
- Impact: An attacker can hold tokens only momentarily at the snapshot to siphon a full period's accrued rewards away from long-term holders.

