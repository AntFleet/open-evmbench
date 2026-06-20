# Audit: 2024-06-vultisig

## Whitelist check lets non-whitelisted buyers pass
- Location: `hardhat-vultisig/contracts/Whitelist.sol` : `checkWhitelist`
- Mechanism: The whitelist rejection condition only checks `_allowedWhitelistIndex == 0 || _whitelistIndex[to] > _allowedWhitelistIndex`. Non-whitelisted addresses have the default index `0`; once `_allowedWhitelistIndex` is set to any positive value, `0 > _allowedWhitelistIndex` is false, so the function does not revert for non-whitelisted buyers.
- Impact: Any non-blacklisted address can buy from the VULT Uniswap pool during the whitelist phase, bypassing the intended allowlist ordering entirely.

## First claimer sweeps other users’ Uniswap fees
- Location: `src/ILOPool.sol` : `claim`
- Mechanism: All NFT positions share one aggregate Uniswap V3 position owned by the `ILOPool`. `claim()` calculates the current tokenId’s entitlement, but then calls `pool.collect(..., type(uint128).max, type(uint128).max)`, collecting all fees owed to the aggregate position. It transfers only the current claimant’s computed amount to the claimant and sends `amountCollected - amount` to `FEE_TAKER`, which includes fees belonging to other tokenIds whose accounting has not been updated.
- Impact: A first claimant can cause other investors’ accrued fees to be swept to the fee taker. Later claimants still calculate entitlement from fee growth, but those tokens are no longer available, causing failed claims or permanent loss of their fees and potentially blocking vested liquidity claims.

## Launch can be blocked by manipulating the public Uniswap pool price
- Location: `src/ILOManager.sol` : `launch`
- Mechanism: `launch()` requires the live Uniswap V3 `slot0.sqrtPriceX96` to equal the project’s configured initial price exactly. The Uniswap pool is public before ILO launch, so an attacker can add liquidity and/or swap a tiny amount to move the pool price away from the exact initialized value. The ILO has no mechanism to restore or tolerate price movement before calling each pool’s launch.
- Impact: Any actor can make a fully funded sale fail to launch, forcing users into the delayed refund path and imposing gas/time losses on all participants.

## Per-user cap is bypassed by transferring the position NFT
- Location: `src/ILOPool.sol` : `buy`
- Mechanism: The per-user contribution cap is enforced against the first NFT currently owned by `recipient`: if `balanceOf(recipient) == 0`, a fresh NFT is minted with a fresh `_positions[tokenId].raiseAmount`. ERC721 transfers are not restricted, so a whitelisted buyer can buy up to `maxCapPerUser`, transfer the NFT away, regain `balanceOf(recipient) == 0`, and buy again into a new position.
- Impact: One whitelisted participant can exceed `maxCapPerUser` arbitrarily and capture more of the sale than intended.

## ILO pools can be created with an impossible launch range
- Location: `src/ILOManager.sol` : `initILOPool`
- Mechanism: The range validation checks `sqrtRatioLowerX96 < initialPoolPriceX96` and `sqrtRatioLowerX96 < sqrtRatioUpperX96`, but never checks `initialPoolPriceX96 < sqrtRatioUpperX96`. If the initial price is at or above the upper tick, `_saleAmountNeeded()` and `launch()` still assume an in-range position, while the actual Uniswap V3 mint is single-sided/out-of-range and fails the raise-token minimum check.
- Impact: A pool can accept contributions but be unable to launch, forcing contributors to wait for refunds and making the sale unusable.

## Unbounded fee BPS can brick claims
- Location: `src/ILOManager.sol` : `initialize`, `setPlatformFee`, `setPerformanceFee`; `src/ILOPool.sol` : `_deductFees`
- Mechanism: Platform and performance fees are never constrained to `<= BPS` (`10000`). `_deductFees()` subtracts `FullMath.mulDiv(amount, feeBPS, BPS)` from `amount` under Solidity `0.7.6`, where arithmetic underflow wraps instead of reverting. A fee above 100% therefore produces nonsensical huge “amount left” values.
- Impact: Projects created with invalid fee settings can have all claims revert or attempt impossible transfers, locking users’ liquidity and fees.

## Manager can be taken over if initialized late
- Location: `src/ILOManager.sol` : `initialize`
- Mechanism: `initialize()` is external, has no `onlyOwner` guard, and the constructor does not disable initialization. The custom `whenNotInitialized` modifier only prevents a second call. If the manager or its proxy is deployed without atomic initialization, any address can be the first caller and set `initialOwner`, fee taker, pool implementation, factory, and WETH address.
- Impact: An attacker can seize ownership and control critical protocol configuration before legitimate initialization, enabling malicious pool implementations, fee redirection, and project disruption.

