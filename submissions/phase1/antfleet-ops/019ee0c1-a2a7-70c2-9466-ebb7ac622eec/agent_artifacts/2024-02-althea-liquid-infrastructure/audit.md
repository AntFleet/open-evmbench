# Audit: 2024-02-althea-liquid-infrastructure

I found one genuine security vulnerability.

## Duplicate holder entries allow reward theft and distribution lock
- Location: `liquid-infrastructure/contracts/LiquidInfrastructureERC20.sol` : `_beforeTokenTransfer`, `_afterTokenTransfer`, `distribute`
- Mechanism: The `holders` array is treated as the canonical holder set, but membership is inferred from `balanceOf(to) != 0` instead of checking whether `to` is already in the array. A zero-value transfer to an approved zero-balance address repeatedly pushes that address into `holders`, because its balance remains zero. The removal logic only processes `from` and can also preserve duplicates during swap-and-pop removal. After creating many duplicate entries for an approved address, the attacker can move a real balance to that address. During `distribute`, the contract iterates over every `holders` entry and pays `erc20EntitlementPerUnit[j] * balanceOf(recipient)` for each entry, so the same balance is paid once per duplicate array entry.
- Impact: An approved holder can overclaim distribution ERC20s by creating duplicate holder entries before a distribution. If the duplicated claims exceed the contract’s distributable balance, later transfers revert and the contract can remain stuck in `LockedForDistribution`, freezing transfers, minting, and burning until the missing distributable tokens are externally replenished. Zero-value transfers or burns can also bloat `holders`, making distributions much more expensive and easier to grief.

