# Audit: 2024-06-vultisig

## Claimers after the first lose their fees and are permanently bricked
- Location: src/ILOPool.sol : `claim`
- Mechanism: All NFT positions are backed by a single shared Uniswap V3 position at `[TICK_LOWER, TICK_UPPER]`. `claim` burns only the caller's slice (`pool.burn(..., liquidity2Claim)`) but then harvests the *entire* position with `pool.collect(address(this), TICK_LOWER, TICK_UPPER, type(uint128).max, type(uint128).max)`, so `amountCollected0/1` include every other holder's accrued fees. The caller is paid their computed `amount0/amount1`, and the remainder `amountCollected0 - amount0` / `amountCollected1 - amount1` is forwarded to `FEE_TAKER`. The first claimer therefore sweeps all other investors' fee entitlements to `FEE_TAKER`. Once those fees are gone, a later claimer still computes `fees = (feeGrowthInside - position.feeGrowthInside0LastX128) * positionLiquidity` (a large value), making `amount0 > amountCollected0`; the unchecked subtraction `amountCollected0 - amount0` (Solidity 0.7.6) underflows to a huge value and the `safeTransfer` to `FEE_TAKER` reverts for insufficient balance.
- Impact: The first `claim` diverts every other holder's trading fees to `FEE_TAKER`, and all subsequent `claim` calls revert, permanently locking those holders' principal and fees in the pool.

## Positions never snapshot `feeGrowthInside` at creation
- Location: src/ILOPool.sol : `buy` and `launch`
- Mechanism: When an investor position is created in `buy` (and project positions in `launch`), the `Position` struct is left with `feeGrowthInside0LastX128 == 0 / feeGrowthInside1LastX128 == 0` instead of being initialized to the pool's current `feeGrowthInside` for the tick range. `claim` later computes fees as `FullMath.mulDiv(feeGrowthInside0LastX128 - position.feeGrowthInside0LastX128, positionLiquidity, Q128)`. Because `initProject` can bind to a pre-existing Uniswap pool (the `else` branch of `_initUniV3PoolIfNecessary` accepts an already-initialized pool), the range's `feeGrowthInside` can be non-zero before this pool's liquidity is ever added, so the delta is inflated by all historical growth.
- Impact: On any pool with pre-existing fee growth, the first claimer's fee calculation is grossly overstated, letting it withdraw fees/principal that belong to others (or revert), corrupting the accounting for every position.

## Unprotected `initialize` allows hijacking the manager
- Location: src/ILOManager.sol : `initialize`
- Mechanism: The constructor only does `transferOwnership(tx.origin)` and never sets `_initialized`, so after deployment `initialize` is callable by anyone (it is guarded by `whenNotInitialized` but has no `onlyOwner`). Whoever calls it first sets `initialOwner`, `FEE_TAKER`, `ILO_POOL_IMPLEMENTATION`, `UNIV3_FACTORY`, and the fee parameters. If deployment and initialization are not performed atomically in one transaction, an attacker can front-run the legitimate `initialize` call and seize ownership while pointing `ILO_POOL_IMPLEMENTATION` at a malicious clone target.
- Impact: An attacker becomes owner of the manager and controls the pool implementation and fee taker, enabling theft from every project/pool subsequently deployed through it.

## `maxCapPerUser` is trivially reset by moving the position NFT
- Location: src/ILOPool.sol : `buy`
- Mechanism: `buy` mints a brand-new position whenever `balanceOf(recipient) == 0`, and the cap is enforced per-position via `require(raiseAmount <= saleInfo.maxCapPerUser - _position.raiseAmount)`. A single whitelisted address can buy up to `maxCapPerUser`, transfer the resulting ERC-721 position to another wallet (so its `balanceOf` returns to 0), then call `buy` again to mint a fresh position with a reset cap, repeating indefinitely (and Sybil addresses achieve the same).
- Impact: A single participant can acquire an unbounded share of the sale up to `hardCap`, defeating the per-user allocation limit and the fairness it is meant to guarantee.

## One unfunded pool blocks launch of the entire project
- Location: src/ILOManager.sol : `launch` (and src/ILOPool.sol : `launch`)
- Mechanism: `ILOManager.launch` iterates over every initialized pool and calls `IILOPool(pool).launch()` in a single loop with no per-pool error isolation. `ILOPool.launch` reverts when `totalRaised < saleInfo.softCap` (or if `_refundTriggered`). Since launch is one atomic batch, any single pool that has not met its soft cap (or has had a refund triggered) causes the whole transaction to revert, so no pool of the project can ever launch while that one lags.
- Impact: A single under-subscribed or refund-triggered sub-pool indefinitely prevents the successful pools of the same project from launching their liquidity, locking all raised funds until the refund deadline.

## Sale cap relies on a manipulable short-window TWAP
- Location: hardhat-vultisig/contracts/Whitelist.sol : `checkWhitelist` (via oracles/uniswap/UniswapV3Oracle.sol : `peek`)
- Mechanism: The per-address ETH cap is enforced with `estimatedETHAmount = IOracle(_oracle).peek(amount)` and `_contributed[to] += estimatedETHAmount`. `UniswapV3Oracle.peek` averages over `period = min(PERIOD, getOldestObservationSecondsAgo(pool))`, so immediately after pool creation the averaging window collapses to a few seconds, making the "TWAP" effectively spot price. An attacker can push the VULT/WETH tick to undervalue VULT in ETH terms across that tiny window, causing `peek` to return a low `estimatedETHAmount` so that `_contributed[to]` barely increases relative to the VULT actually bought.
- Impact: During the whitelist phase an attacker can purchase far more than the intended `_maxAddressCap` (default 3 ETH) worth of VULT by deflating the oracle estimate that gates the cap.

