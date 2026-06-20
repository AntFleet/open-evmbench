# Audit: 2024-02-althea-liquid-infrastructure

**Broken require check in releaseManagedNFT allows silent failure to enforce list membership**

- Location: `LiquidInfrastructureERC20.sol` : `releaseManagedNFT`
- Mechanism: After `nft.transferFrom(...)`, the code runs an unconditional `require(true, "unable to find released NFT in ManagedNFTs")` instead of checking a boolean flag set inside the removal loop. The loop performs a swap-and-pop only when a match is found, but never sets any success indicator.
- Impact: Owner can call `releaseManagedNFT` on any NFT the contract owns (even one never added to `ManagedNFTs`), the transfer succeeds, the list is left unchanged, and the call never reverts. This breaks the documented invariant that only ManagedNFTs are released and allows the contract to lose custody of NFTs while the on-chain list remains inconsistent.

**Disapproved holders cause permanent loss of distribution entitlements**

- Location: `LiquidInfrastructureERC20.sol` : `distribute` (and `disapproveHolder`)
- Mechanism: `distribute` only transfers to a recipient when `isApprovedHolder(recipient)` is true; otherwise it simply advances `nextDistributionRecipient` without sending the calculated `entitlement`. `disapproveHolder` only flips the mapping flag and does not remove the address from `holders` or allocate its share elsewhere. `_afterTokenTransfer` only removes addresses that reach zero balance.
- Impact: Any holder that is disapproved while still in the `holders` array will have its proportional share of every `distributableERC20s` token left permanently in the `LiquidInfrastructureERC20` contract. Those tokens become unrecoverable by anyone (no withdrawal or rescue path exists).

**Array modification during iteration in `_afterTokenTransfer` can leave stale holder entries**

- Location: `LiquidInfrastructureERC20.sol` : `_afterTokenTransfer`
- Mechanism: The removal loop iterates with `for (uint i = 0; i < holders.length; i++)`, performs a swap-and-pop when a match is found, but contains no `break` (or index adjustment) after the pop. Length changes mid-iteration.
- Impact: Under certain orderings (especially if duplicate addresses were ever present, or when `from` equals the element swapped in from the end), a zero-balance address can remain in `holders`. Subsequent `distribute` calls will attempt to send to it (or waste gas), and the supply-vs-holder accounting invariants can be violated.

**Mint/burn lock can be bypassed via direct `_mint`/`_burn` paths after a distribution window**

- Location: `LiquidInfrastructureERC20.sol` : `mint`, `burn`, `burnFrom`, `_beforeMintOrBurn`
- Mechanism: The only guard on minting/burning is `_beforeMintOrBurn` which calls `_isPastMinDistributionPeriod`. Once `LastDistribution` is updated by `_endDistribution`, any subsequent call (even in the same block or before the next period) passes the check. The convenience wrappers `mintAndDistribute` etc. also rely on the same check.
- Impact: An owner can mint or burn immediately after finishing a distribution without waiting for the next `MinDistributionPeriod`, violating the documented “supply changes only after distribution” rule and allowing dilution or supply reduction at attacker-chosen times.

**No reentrancy protection on ERC-20 `transfer` calls inside distribution loop**

- Location: `LiquidInfrastructureERC20.sol` : `distribute`
- Mechanism: While `distribute` itself is `nonReentrant`, the inner loop performs `IERC20(toDistribute).transfer(recipient, entitlement)` to arbitrary `recipient` addresses (which may be contracts) without any additional guard. The outer `ReentrancyGuard` only protects the `distribute` entry point.
- Impact: A malicious recipient token can re-enter the contract via a different function (e.g., `withdrawFromManagedNFTs`, `addManagedNFT`, or even `transfer` if the lock state permits) while the distribution accounting (`nextDistributionRecipient`, `LockedForDistribution`) is in an intermediate state, potentially causing duplicate payouts or inconsistent holder lists.
