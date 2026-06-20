# Audit: 2024-06-vultisig

 ## Shared-position fee accounting locks/steals later claims (Critical)
- Location: `src/ILOPool.sol` : `claim`
- Mechanism: All NFTs in an ILO pool share a single Uniswap V3 position owned by the pool contract. `claim` burns only the claimant’s liquidity, computes that NFT’s fee share using its personal `feeGrowthInside` snapshot, then calls `pool.collect(type(uint128).max, ...)`, which withdraws the *entire* uncollected balance of the shared position. It pays the computed `amount0/1` to the claimant and sends the remainder to `FEE_TAKER`. Because `pool.burn` updates the shared position’s `feeGrowthInside` snapshot to the current global value, every other NFT’s stored snapshot becomes stale: later claimants compute fees that include amounts already swept by earlier claims, while `pool.collect` no longer holds those tokens, causing `amountCollected - amount` to underflow and revert. Even if enough new fees later accrue, fees belonging to other positions are redirected to the fee taker.
- Impact: Early claimants can withdraw principal plus their fee share, but later claimants may be permanently unable to claim (principal locked), and the fee taker receives fees that rightfully belong to other investors. The vesting/refund accounting is fundamentally broken for any pool with more than one NFT.

## Reentrancy in `buy` bypasses `maxCapPerUser` (High)
- Location: `src/ILOPool.sol` : `buy`
- Mechanism: When the recipient has no NFT, `buy` calls `_mint` before checking or updating `_position.raiseAmount`. `ERC721._mint` invokes `onERC721Received` on a contract recipient after assigning the token. During that callback the contract can reenter `buy`; the same `tokenId` already exists but its `_position.raiseAmount` is still `0`, so the `maxCapPerUser` check passes again. When the outer call resumes it also increments `_position.raiseAmount`, letting the same address exceed the per-user cap.
- Impact: A whitelisted contract-buyer can accumulate a larger allocation than `maxCapPerUser` allows (still bounded by `hardCap`), undermining the per-investor allocation limit.

## `ILOManager.initialize` is front-runnable / lacks access control (High)
- Location: `src/ILOManager.sol` : `initialize`
- Mechanism: The constructor does not disable initialization (`_initialized` remains `false`) and `initialize` has no access-control check. Anyone can call it before the deployer/intended initializer.
- Impact: An attacker can set themselves as owner, choose the fee taker, set fee rates, and point `ILO_POOL_IMPLEMENTATION` to a malicious implementation, effectively taking over the protocol.

## Refund-deadline overflow enables instant refunds (High)
- Location: `src/ILOManager.sol` : `initProject`
- Mechanism: `uint64 refundDeadline = params.launchTime + DEFAULT_DEADLINE_OFFSET;` uses unchecked `uint64` arithmetic. If `launchTime` is near `type(uint64).max`, `refundDeadline` silently wraps to a very small value.
- Impact: `ILOPool`’s `refundable` modifier then allows refunds long before the intended sale/launch period, letting users and the project admin drain/abort the pool before launch.

## Permissionless project creation allows pool squatting and fake projects (High)
- Location: `src/ILOManager.sol` : `initProject`
- Mechanism: `initProject` has no authorization and uses the UniV3 pool address as the project ID. `_cacheProject` reverts if a project already exists for that pool, so the first caller becomes the permanent, irrevocable admin for the pair.
- Impact: A malicious actor can front-run a legitimate issuer for a token pair, seize admin rights, create fraudulent ILO pools, and block the legitimate project from using the protocol.

## Exact-price `launch` check is permanently DoS-able (Medium)
- Location: `src/ILOManager.sol` : `launch`
- Mechanism: `launch` requires the pool’s current `sqrtPriceX96` to be *exactly* equal to the cached `initialPoolPriceX96`. The Uniswap V3 pool is public, so anyone can add liquidity or swap to move the price by even one bit after `launchTime`.
- Impact: A griefer can permanently block launch by moving the price away from the initial value, forcing investors to wait until the refund deadline to recover funds.

## Owner-controlled fee settings can freeze or steal claims (Medium)
- Location: `src/ILOManager.sol` : `setPlatformFee`, `setPerformanceFee`, `setFeeTaker`; `src/ILOPool.sol` : `claim`
- Mechanism: `PLATFORM_FEE` and `PERFORMANCE_FEE` are `uint16` with no upper-bound validation, while `_deductFees` assumes `feeBPS <= 10000`; setting a fee above `10000` makes every `claim` revert. Separately, `FEE_TAKER` is mutable by the owner and is the unconditional final transfer target in `claim`.
- Impact: A compromised or malicious owner can freeze all withdrawals by setting a fee above `10000` or by pointing `FEE_TAKER` to a reverting address, or steal all proceeds by setting fees to `10000`.

## Self-whitelist requires no ETH (Low)
- Location: `hardhat-vultisig/contracts/Whitelist.sol` : `receive()`
- Mechanism: The receive function does not enforce `msg.value > 0`; it adds the sender to the whitelist and refunds whatever was sent, including zero.
- Impact: When self-whitelist is enabled, anyone can whitelist an unlimited number of addresses for free, defeating any economic gate the whitelist was meant to impose.

## Blacklist and cap only apply to direct pool transfers (Low)
- Location: `hardhat-vultisig/contracts/Whitelist.sol` : `checkWhitelist`
- Mechanism: The blacklist and `maxAddressCap` checks are only executed when `from == _pool`. Transfers from any other address—such as a whitelisted router, aggregator, or friend—are unrestricted.
- Impact: A blacklisted user can still receive tokens indirectly, and the per-address contribution cap can be bypassed by routing buys through a whitelisted intermediary.
