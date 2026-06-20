# Audit: 2024-06-vultisig

## Unwhitelisted buyers pass the whitelist check
- Location: `hardhat-vultisig/contracts/Whitelist.sol` : `checkWhitelist`
- Mechanism: Unwhitelisted addresses have `_whitelistIndex[to] == 0`, but the check only reverts when `_allowedWhitelistIndex == 0` or `_whitelistIndex[to] > _allowedWhitelistIndex`. Once the owner sets any nonzero allowed index, index `0` addresses pass because `0 > allowedIndex` is false.
- Impact: Any non-blacklisted address can buy during the whitelist period, bypassing the whitelist entirely.

## Contribution cap is enforced with an undercountable pool TWAP instead of actual input
- Location: `hardhat-vultisig/contracts/Whitelist.sol` : `checkWhitelist`; `hardhat-vultisig/contracts/oracles/uniswap/UniswapV3Oracle.sol` : `peek`
- Mechanism: The cap accounting adds `IOracle(_oracle).peek(amount)` based on VULT output amount, not the actual ETH/WETH paid by the buyer. The oracle also discounts the TWAP by 5% via `* 95`, so even honest prices undercount contribution size; if the pool TWAP is manipulated or stale, the undercount can be larger.
- Impact: Buyers can acquire more than `_maxAddressCap` worth of tokens while `_contributed[to]` remains within the cap.

## `ILOManager` can be seized before initialization
- Location: `src/ILOManager.sol` : `initialize`
- Mechanism: `initialize` is external, protected only by `whenNotInitialized`, and is not restricted to the constructor owner. Any uninitialized deployment can be initialized by the first caller, who chooses `initialOwner`, fee taker, pool implementation, Uniswap factory, and WETH address.
- Impact: An attacker can take full manager ownership and configure malicious protocol dependencies and fee recipients.

## Projects can be squatted by arbitrary callers
- Location: `src/ILOManager.sol` : `initProject`
- Mechanism: `initProject` is permissionless and permanently caches one project per Uniswap V3 pool address. The project admin is set to `msg.sender`, with no proof that the caller controls the sale token or is authorized to launch that project.
- Impact: An attacker can pre-create a project for another token pair/fee tier and block the legitimate issuer from using that pool through this manager.

## Per-user cap can be bypassed by transferring the position NFT away
- Location: `src/ILOPool.sol` : `buy`
- Mechanism: The pool treats `balanceOf(recipient) == 0` as proof that the recipient has no prior allocation. A whitelisted buyer can buy up to `maxCapPerUser`, transfer the NFT to another address, then buy again as the same recipient, causing a fresh NFT with `_position.raiseAmount == 0` to be minted.
- Impact: A whitelisted participant can exceed `maxCapPerUser` and monopolize more of the sale than intended.

## Launch is still allowed after the refund deadline
- Location: `src/ILOPool.sol` : `launch`; `src/ILOPool.sol` : `refundable`
- Mechanism: Refunds become available after `refundDeadline`, but `launch` only checks `_refundTriggered`, not whether the refund deadline has passed. After the deadline, launch and refund are a race: if anyone calls `launch` first, `_launchSucceeded` blocks all refunds.
- Impact: Users can lose their expected refund right after the deadline if the project or any caller launches first.

## Invalid upper tick can launch a one-sided pool with no sale tokens
- Location: `src/ILOManager.sol` : `initILOPool`; `src/ILOPool.sol` : `launch`
- Mechanism: `initILOPool` checks `sqrtRatioLowerX96 < initialPoolPriceX96` but never checks `initialPoolPriceX96 < sqrtRatioUpperX96`. If `SALE_TOKEN` is token0 and the configured price is at/above the upper tick, Uniswap mints a position containing only token1, the raise token. Because `amount0Min` for the sale token remains zero, launch succeeds and `_refundProject` returns the unused sale tokens to the admin.
- Impact: Investors can fund a sale that launches without depositing the promised sale-token side of liquidity; the admin gets the sale tokens back while raised funds are locked in the pool.

## Shared Uniswap position fee accounting lets one claimant sweep everyone’s fees
- Location: `src/ILOPool.sol` : `claim`
- Mechanism: All NFT positions are backed by one aggregate Uniswap V3 position owned by the pool contract. On any claim, the contract calls `pool.burn(...)` and then `pool.collect(..., type(uint128).max, type(uint128).max)`, collecting all accrued fees for the aggregate position. It only credits the current NFT’s computed fee share to the claimant and sends the remaining collected tokens to `FEE_TAKER`. Other NFTs keep stale `feeGrowthInsideLast` values and later try to claim fees that were already collected.
- Impact: The first claimant after fees accrue can cause other investors’ fees to be redirected to the fee taker and can make later claims revert or underpay.

## Historical Uniswap fee growth is overcredited to internal NFTs
- Location: `src/ILOPool.sol` : `launch`; `src/ILOPool.sol` : `claim`
- Mechanism: Internal positions start with `feeGrowthInside0LastX128` and `feeGrowthInside1LastX128` equal to zero. If the underlying Uniswap pool existed before launch and already had nonzero fee growth inside the range, `claim` computes fees from zero instead of from the aggregate position’s fee-growth baseline at mint time.
- Impact: Claimants can be credited for fees the ILO position never earned, causing claim reverts or draining tokens that belong to other accounting buckets if the contract holds enough balance.

## Fee-on-transfer raise tokens make sale accounting insolvent
- Location: `src/ILOPool.sol` : `buy`; `src/ILOPool.sol` : `claimRefund`; `src/ILOPool.sol` : `launch`
- Mechanism: `buy` credits `raiseAmount` to `totalRaised` and `_position.raiseAmount` before transferring tokens, and it never checks the actual balance delta received. With fee-on-transfer or otherwise deflationary raise tokens, the pool records more raised funds than it actually received.
- Impact: Launch can fail due to insufficient raise-token balance, and refunds can become insolvent because users are owed the credited amount rather than the amount the contract actually received.

