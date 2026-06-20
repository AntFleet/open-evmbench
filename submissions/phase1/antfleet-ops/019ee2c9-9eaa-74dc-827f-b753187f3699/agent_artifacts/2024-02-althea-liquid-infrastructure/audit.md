# Audit: 2024-02-althea-liquid-infrastructure

## ERC721 transfer approval also grants full control over NFT-held funds
- Location: `liquid-infrastructure/contracts/LiquidInfrastructureNFT.sol` : `withdrawBalances`, `withdrawBalancesTo`, `setThresholds`
- Mechanism: These functions gate access with `_isApprovedOrOwner(..., AccountId)` / `onlyOwnerOrApproved(AccountId)`, so any address approved to transfer the NFT, or approved-for-all by the owner, is treated as an administrator of the liquid account. In ERC721 flows, approvals are commonly granted to marketplaces, brokers, escrow contracts, or other temporary operators. Here that same approval lets the operator call `withdrawBalancesTo(..., attacker)` to send all ERC20 revenue out of the NFT, and also call `setThresholds(...)` to change the x/microtx sweep configuration for future revenue.
- Impact: Any approved NFT operator can steal all currently accrued ERC20 balances from the NFT and can reconfigure thresholds to capture or disrupt future revenue, without ever taking ownership of the NFT itself.

## Any token holder can permanently bloat `holders` with `address(0)` entries and DoS distributions
- Location: `liquid-infrastructure/contracts/LiquidInfrastructureERC20.sol` : `_beforeTokenTransfer`, `_afterTokenTransfer`, `distribute`
- Mechanism: On every burn, `_beforeTokenTransfer` executes with `to == address(0)`, then unconditionally runs `holders.push(to)` because `balanceOf(address(0))` is always zero. Those zero-address entries are not removed by the burn path, so an approved holder can repeat `burn(1)` to append arbitrarily many junk entries at very low economic cost. Later, `distribute()` iterates over the full `holders` array, and `_afterTokenTransfer` does an O(n) scan whenever a sender’s balance reaches zero. Because `_isPastMinDistributionPeriod()` only checks `holders.length`, these junk entries also keep the contract in the “must distribute before minting or burning” state once the period elapses.
- Impact: Any approved holder can force the `holders` array to grow until distributions become too expensive to complete, freezing transfers during an in-progress distribution and eventually making mint/burn operations impractical or impossible once the minimum distribution period has passed.

