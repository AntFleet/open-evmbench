# Audit: 2024-02-althea-liquid-infrastructure

## Duplicate holder entries allow repeated reward claims
- Location: `LiquidInfrastructureERC20.sol` : `_beforeTokenTransfer`, `distribute`
- Mechanism: `_beforeTokenTransfer` appends `to` to `holders` whenever `balanceOf(to) == 0`, but it does not check `amount > 0` and does not deduplicate the array. An approved account can repeatedly `transfer(0)` to another approved zero-balance address, creating many `holders` entries for that same recipient before it receives any real balance. During `distribute`, the contract iterates array entries, not unique holders, and pays `erc20EntitlementPerUnit[j] * balanceOf(recipient)` for every occurrence.
- Impact: An attacker with approved addresses can receive the same reward entitlement multiple times, draining distributable ERC20 balances ahead of later holders. If the duplicate claims exceed available balances, later payout transfers can revert and leave the distribution unable to complete.

## Zero-amount burns can permanently bloat the holder list
- Location: `LiquidInfrastructureERC20.sol` : `_beforeTokenTransfer`, `_afterTokenTransfer`, `distribute`
- Mechanism: Burns call the hook with `to == address(0)`. The code skips the allowlist check for `address(0)`, but still runs `if (balanceOf(to) == 0) holders.push(to)`, so every burn appends `address(0)`. `burn(0)` is enough and can be called without spending tokens whenever mint/burn is not blocked by the distribution period. `_afterTokenTransfer` only tries to remove `from`, so the zero-address entries remain.
- Impact: An attacker can cheaply grow `holders` with useless entries. Every distribution must iterate those entries before `_endDistribution` can unlock the token, so the system can be pushed into out-of-gas distribution attempts, freezing transfers, mints, burns, and reward payout progress.

## Reward math truncates entitlements before applying balances
- Location: `LiquidInfrastructureERC20.sol` : `_beginDistribution`
- Mechanism: The contract computes `erc20EntitlementPerUnit` as `balance / totalSupply()` and later multiplies that truncated integer by each holder balance. This divide-before-multiply formula loses all fractional entitlement. With an 18-decimal share token and lower-decimal or smaller reward balances, `balance / supply` can be zero even when meaningful rewards exist.
- Impact: Distributions can complete while paying every holder zero, updating `LastDistribution` as if the period was settled. Remaining rewards stay in the contract and may later be shared with a different supply, allowing later holders to receive revenue accrued before they held shares and underpaying the original holders.

## Reverting reward-token transfers can brick an active distribution
- Location: `LiquidInfrastructureERC20.sol` : `distribute`
- Mechanism: `distribute` directly calls `IERC20(distributableERC20s[j]).transfer(recipient, entitlement)` with no way to skip a reverting payout. If distribution is processed in batches, earlier batches can commit `LockedForDistribution = true` and advance `nextDistributionRecipient`; a later batch that reaches a blacklisted recipient, incompatible token, or otherwise reverting reward token will always revert at the same index.
- Impact: The contract can remain stuck with `LockedForDistribution == true`, which blocks all transfers, mints, and burns. Rewards also cannot progress past the failing recipient unless the owner changes state out of band, such as disapproving the recipient or changing the token list.

## Failed ERC20 transfers are treated as settled payouts
- Location: `LiquidInfrastructureERC20.sol` : `distribute`
- Mechanism: If a distributable ERC20 returns `false` instead of reverting, the code merely leaves `receipts[j]` as zero and continues. At the end of the holder loop, `_endDistribution` clears entitlements and advances `LastDistribution` even though the recipient was not paid.
- Impact: Holders can be silently underpaid while the contract records the epoch as complete. The unpaid tokens remain pooled for a future distribution against whatever holder set and supply exist then, causing reward misallocation.

## Token list can be changed mid-distribution, corrupting the payout snapshot
- Location: `LiquidInfrastructureERC20.sol` : `setDistributableERC20s`, `distribute`
- Mechanism: `_beginDistribution` snapshots only per-index entitlement values for the current `distributableERC20s`, but `setDistributableERC20s` is callable while `LockedForDistribution == true`. A later distribution batch then pairs old entitlement indexes with a new token list; if the new list is longer, `erc20EntitlementPerUnit[j]` reads out of bounds, and if reordered or same-length, entitlements for one token are applied to another.
- Impact: A compromised or mistaken owner can freeze an in-progress distribution or mispay rewards from the wrong token balances, leaving the ERC20 locked until the list is restored correctly.

