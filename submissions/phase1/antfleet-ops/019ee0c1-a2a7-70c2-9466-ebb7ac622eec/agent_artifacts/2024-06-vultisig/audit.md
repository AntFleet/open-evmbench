# Audit: 2024-06-vultisig

## Unprotected manager initialization takeover
- Location: `src/ILOManager.sol` : `initialize`
- Mechanism: `initialize()` is external, only gated by `whenNotInitialized()`, and the constructor does not mark the manager initialized. Any address that calls it first can set `FEE_TAKER`, `ILO_POOL_IMPLEMENTATION`, Uniswap factory/WETH addresses, fee values, and then `transferOwnership(initialOwner)` to itself.
- Impact: An attacker can front-run or call initialization on an uninitialized deployment and fully take over the launchpad manager.

## Per-user sale cap can be bypassed by transferring the position NFT
- Location: `src/ILOPool.sol` : `buy`
- Mechanism: The cap is enforced against `_positions[tokenId].raiseAmount`, where `tokenId` is selected from `balanceOf(recipient)`. If the recipient has no NFT, a fresh position is minted. Because the position NFT is freely transferable, a whitelisted buyer can buy up to `maxCapPerUser`, transfer the NFT away, then buy again as the same recipient and receive a new position with a reset `raiseAmount`.
- Impact: A single whitelisted address can bypass `maxCapPerUser` and consume far more than its intended allocation, up to the pool hard cap.

## Broken aggregate fee accounting can confiscate other users’ fees and DoS later claims
- Location: `src/ILOPool.sol` : `claim`
- Mechanism: The contract owns one aggregate Uniswap V3 position but tracks fee growth per NFT. On every claim it calls `pool.collect(..., type(uint128).max, type(uint128).max)`, collecting all fees owed to the aggregate position, not just the caller’s share. It then transfers the caller’s computed amount and sends `amountCollected - amount` to `FEE_TAKER`. That remainder can include fees belonging to every other NFT holder.
- Impact: The first claimer can cause other users’ accrued fees to be sent to the fee taker. Later users may revert or receive corrupted payouts because their per-NFT accounting still expects fees that have already been collected and removed.

## Pre-launch Uniswap fee growth poisons claim accounting
- Location: `src/ILOPool.sol` : `launch`, `claim`
- Mechanism: Investor NFTs are created before the Uniswap V3 LP position exists, with `feeGrowthInside0LastX128` and `feeGrowthInside1LastX128` left at zero. At launch, Uniswap initializes the aggregate position’s fee-growth baseline to the pool’s current fee growth. If anyone generated pool fee growth before launch, later `claim()` subtracts the NFT’s zero baseline from the current pool baseline and treats pre-launch fee growth as earned by the ILO position.
- Impact: An attacker who can create pre-launch pool activity can make claims over-account fees that the ILO position never earned, causing claim reverts or misallocated payouts.

## Permissionless project squatting can block legitimate launches
- Location: `src/ILOManager.sol` : `initProject`
- Mechanism: Anyone can initialize a project for any `saleToken` / `raiseToken` / fee tier. `_cacheProject()` permanently binds the resulting Uniswap V3 pool address to `msg.sender` as admin, and future attempts for the same pool revert with `RE`. The caller does not need to prove control over the sale token.
- Impact: An attacker can front-run or preempt a real project by registering its token pair first, forcing the legitimate team to use another fee tier/pair or abandon that manager instance.

## Launch can be permanently blocked by moving the Uniswap pool price
- Location: `src/ILOManager.sol` : `launch`
- Mechanism: `launch()` requires the live Uniswap V3 pool `slot0().sqrtPriceX96` to equal the cached `initialPoolPriceX96` exactly. The pool is public before launch; if an attacker adds liquidity and swaps so the price differs even slightly, the equality check reverts.
- Impact: An attacker can grief a project launch and force the sale toward the refund path unless the exact initial price is restored.

## Whitelist, blacklist, and lock only apply to one configured pool
- Location: `hardhat-vultisig/contracts/Whitelist.sol` : `checkWhitelist`
- Mechanism: All restrictions are inside `if (from == _pool && to != owner())`. For any transfer where `from` is not the single configured pool, the function does nothing, including when `_locked` is true or the recipient is blacklisted/not whitelisted.
- Impact: Once tokens exist outside the configured pool, they can be transferred OTC or traded through another pool to non-whitelisted or blacklisted addresses during the supposed locked/whitelist period.

## Max ETH cap uses an oracle estimate instead of actual swap input
- Location: `hardhat-vultisig/contracts/Whitelist.sol` : `checkWhitelist`; `hardhat-vultisig/contracts/oracles/uniswap/UniswapV3Oracle.sol` : `peek`
- Mechanism: The contribution cap records `IOracle(_oracle).peek(amount)`, where `amount` is the VULT output transferred from the pool. It does not know the actual ETH/WETH paid into the swap. With exact-input swaps, price impact, spot/TWAP divergence, or a short/manipulated TWAP window, actual ETH spent can exceed the recorded estimate.
- Impact: A buyer can spend more than `_maxAddressCap` worth of ETH while the whitelist contract records a lower contribution, bypassing the intended per-address ETH cap.

