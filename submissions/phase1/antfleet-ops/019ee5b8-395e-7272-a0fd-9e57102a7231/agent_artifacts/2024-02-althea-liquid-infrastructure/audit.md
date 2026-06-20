# Audit: 2024-02-althea-liquid-infrastructure

## Holder list manipulation via zero-amount transfers and burns

- Location: `liquid-infrastructure/contracts/LiquidInfrastructureERC20.sol` : `_beforeTokenTransfer`, `distribute`
- Mechanism: `_beforeTokenTransfer` adds `to` to `holders` whenever `balanceOf(to) == 0`, without checking `amount > 0`, without checking actual holder-list membership, and without excluding `address(0)`. ERC20 permits zero-amount `transferFrom`, so an approved holder can repeatedly call `transferFrom(anyAddress, self, 0)` before receiving tokens and insert duplicate entries for themselves. Later, once they hold a balance, `distribute` iterates each duplicate entry and pays `erc20EntitlementPerUnit[j] * balanceOf(recipient)` every time. Separately, any caller can call `burn(0)` while mint/burn is not distribution-blocked, causing `to == address(0)` to be appended repeatedly; `_afterTokenTransfer` only tries to remove `from`, so these zero-address entries remain.
- Impact: An approved holder can receive the same distribution multiple times and steal rewards owed to other holders. The same bug also lets attackers bloat `holders` with junk entries, making `distributeToAllHolders` run out of gas and making batched distributions expensive or impractical; if a distribution cannot finish, `LockedForDistribution` keeps transfers, mints, and burns frozen.

