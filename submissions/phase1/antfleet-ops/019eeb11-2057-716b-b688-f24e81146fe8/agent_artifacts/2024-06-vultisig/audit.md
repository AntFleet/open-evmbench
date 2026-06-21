# Audit: 2024-06-vultisig
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Aggregate Uniswap fee collection sweeps other positions' fees to FEE_TAKER and bricks later claims
*(consensus, 6 of 6 reports)*
- Location: `src/ILOPool.sol` : `claim` (the `pool.burn(TICK_LOWER, TICK_UPPER, liquidity2Claim)` + `pool.collect(address(this), TICK_LOWER, TICK_UPPER, type(uint128).max, type(uint128).max)` block and the trailing `safeTransfer(... feeTaker, amountCollected0 - amount0)` lines)
- Mechanism: Every ILO NFT (all investor positions plus project vesting positions) is a virtual sub-position of a single real Uniswap V3 position owned by the pool at one `(TICK_LOWER, TICK_UPPER)`. When any one holder claims, `pool.burn` realizes the *entire* aggregate position's accrued fees into `tokensOwed`, and `pool.collect(..., max, max)` pulls all of them into the contract. The caller is credited only their own computed `fees0/fees1`, and the surplus `amountCollected0 - amount0` (everyone else's fees) is shipped to `FEE_TAKER`. A subsequent claimant's computed `amount0` can then exceed the freshly collected `amountCollected0`, so `amountCollected0 - amount0` underflows (0.7.6, unchecked) and the transfer reverts.
- Impact: The first caller to `claim` (even a dust position) drains all unclaimed holders' trading fees to `FEE_TAKER`, a permanent loss; the second and every subsequent `claim` then reverts on underflow, permanently locking principal and fees for all remaining positions.

## ILOManager.initialize has no access control — front-runnable ownership / fee hijack
*(consensus, 6 of 6 reports)*
- Location: `src/ILOManager.sol` : `initialize` (guarded only by `whenNotInitialized()`) and `constructor` (`transferOwnership(tx.origin)`)
- Mechanism: The constructor sets `owner = tx.origin`, but `initialize` has no `onlyOwner` or any caller check. It sets `FEE_TAKER`, `ILO_POOL_IMPLEMENTATION`, `UNIV3_FACTORY`, `WETH9`, the fee parameters, and calls `transferOwnership(initialOwner)` with a caller-supplied address. Deployment (CREATE2, deterministic address) and initialization are separate transactions (`Deploy.s.sol` / `Init.s.sol`), so an attacker can front-run the legitimate `initialize`; `_initialized = true` then locks out the real init.
- Impact: Full, permanent takeover of the manager: attacker becomes owner, can point `ILO_POOL_IMPLEMENTATION` at a malicious clone target (every cloned pool runs attacker code over user funds), redirect `FEE_TAKER` to themselves, and set arbitrary fees — compromising every project created under the manager.

## Per-position fee-growth baseline (`feeGrowthInside*LastX128`) never initialized at mint
*(consensus, 5 of 6 reports)*
- Location: `src/ILOPool.sol` : `buy` / `launch` (positions created without seeding `feeGrowthInside0LastX128`/`1LastX128`) and `claim` (fee delta `mulDiv(feeGrowthInside_now - position.feeGrowthInside*LastX128, positionLiquidity, Q128)`)
- Mechanism: New positions in `buy` and `launch` leave `feeGrowthInside*LastX128` at 0; the correct baseline is the pool's `feeGrowthInside` *at mint time*. This is masked only for a freshly created pool (baseline ≈ 0). `ILOManager._initUniV3PoolIfNecessary` explicitly supports reusing an existing pool, which may already have nonzero fee growth.
- Impact: For an ILO launched over a pre-existing pool with prior in-range fee growth, the first `claim` computes a massively inflated `fees0/fees1` (delta measured from 0). The contract cannot back that amount, so the claim either drains unrelated token balances or underflows/reverts — bricking withdrawals and stranding liquidity. An attacker can deliberately pre-accrue fee growth before launch.

## `maxCapPerUser` bypassable by transferring/cycling the position NFT
*(consensus, 5 of 6 reports)*
- Location: `src/ILOPool.sol` : `buy` (the `balanceOf(recipient) == 0` mint branch and `require(raiseAmount <= saleInfo.maxCapPerUser - _position.raiseAmount, "UC")`)
- Mechanism: The per-user cap is enforced against the `raiseAmount` of the single NFT the recipient currently holds; `buy` mints a fresh NFT (with `raiseAmount == 0`) whenever `balanceOf(recipient) == 0`. ILO position NFTs are freely transferable during the sale, and the whitelist check is on `recipient`, not the holder. A buyer can buy up to the cap, transfer the NFT away, and buy again under a fresh 0 cap, repeating up to `hardCap`.
- Impact: A single whitelisted participant can acquire an unbounded share of the sale (up to the hard cap), defeating the anti-whale `maxCapPerUser` control and crowding out other buyers; allocations can also end up owned by non-whitelisted addresses.
- Reviewer disagreement: 1 of 6 (opus shot 3) judged `buy`'s cap subtraction sound — but it evaluated only the `raiseAmount ≤ maxCapPerUser` arithmetic invariant and did not consider NFT-transfer cycling.

## `setPlatformFee` / `setPerformanceFee` (and `initialize`) accept fees > 100% (BPS), bricking claims via underflow
*(consensus, 5 of 6 reports)*
- Location: `src/ILOManager.sol` : `setPlatformFee` / `setPerformanceFee` (and `initialize` parameters); consumed in `src/ILOPool.sol` : `_deductFees`
- Mechanism: Neither setter (nor `initialize`) bounds `PLATFORM_FEE`/`PERFORMANCE_FEE` against `BPS` (10000). `_deductFees` computes `amount - FullMath.mulDiv(amount, feeBPS, BPS)`; if `feeBPS > BPS` the subtrahend exceeds `amount` and the subtraction underflows (0.7.6, unchecked) to a near-`type(uint256).max` value that fails the transfer. Fees are snapshotted into each `Project` at creation, so a bad value is baked into every pool created afterward.
- Impact: A single fat-fingered, misconfigured, compromised, or attacker-hijacked owner setting a fee ≥ 10000 BPS permanently bricks `claim`/fee-deduction for every position in every subsequently created project — funds become unwithdrawable.
- Reviewer disagreement: 1 of 6 (opus shot 3) examined `_deductFees` and called it harmless — but only assessed the fee *rounding direction* (rounds down, favors user), not the missing upper bound.

## Exact `sqrtPriceX96` equality in `launch` enables permissionless launch griefing
*(consensus, 4 of 6 reports)*
- Location: `src/ILOManager.sol` : `launch` (the `require(initialPoolPriceX96 == sqrtPriceX96, "UV3P")` check)
- Mechanism: `launch` requires the live `slot0().sqrtPriceX96` to equal the cached `initialPoolPriceX96` *exactly*. Before launch the ILO has deposited no liquidity, so the pool price can be moved essentially for free (a swap with a chosen `sqrtPriceLimit` against an empty range, or after seeding a tiny out-of-range position). A 1-wei deviation is enough, and an attacker can re-grief after each correction; `ILOManager` has no multicall to atomically reset price and launch.
- Impact: Permissionless DoS on project launch even after the soft cap is met; a determined attacker can stall launches indefinitely and force projects onto the refund path.

## Unchecked `uint16 * uint128` intermediate in `_unlockedLiquidity` can overflow (0.7.6)
*(consensus, 3 of 6 reports)*
- Location: `src/ILOPool.sol` : `_unlockedLiquidity` (linear-vest branch `FullMath.mulDiv(vest.shares * totalLiquidity, block.timestamp - vest.start, (vest.end - vest.start) * BPS)`)
- Mechanism: `vest.shares` (`uint16`) times `totalLiquidity` (`uint128`) is evaluated in `uint128` arithmetic *before* being widened to `uint256` for `mulDiv`. Under 0.7.6 there are no overflow checks, so when `totalLiquidity > 2^128 / vest.shares` (≈ `3.4e34` for max shares — within the valid `uint128` liquidity range for a tight-range, large raise) the product silently wraps, defeating `mulDiv`'s 512-bit precision. The fully-vested sibling branch passes operands to `mulDiv` separately and is unaffected, making the inconsistency the tell.
- Impact: For large-liquidity positions the linear-vest unlock amount is corrupted, miscomputing `_claimableLiquidity`/`vestingStatus` and letting a position over- or under-claim its vested share (or revert), mis-vesting/locking liquidity. Fix: widen one operand (`uint256(vest.shares) * totalLiquidity`).

## Whitelist index-0 sentinel lets non-whitelisted addresses pass `checkWhitelist`
*(consensus, 3 of 6 reports)*
- Location: `hardhat-vultisig/contracts/Whitelist.sol` : `checkWhitelist` (the `if (_allowedWhitelistIndex == 0 || _whitelistIndex[to] > _allowedWhitelistIndex) revert NotWhitelisted();` check)
- Mechanism: `0` is the "not whitelisted" sentinel, but the guard only reverts when `_allowedWhitelistIndex == 0` or `_whitelistIndex[to] > _allowedWhitelistIndex`. Once the owner sets `_allowedWhitelistIndex >= 1` (required for any whitelisted user to buy), a non-whitelisted address (`index 0`) satisfies `0 > N == false` and passes. The missing `_whitelistIndex[to] == 0` check is the bug.
- Impact: Any non-blacklisted address can buy VULT from the pool during the gated sale without ever being whitelisted (bounded only by the per-address ETH cap), defeating the entire whitelist restriction. Preconditions: `_locked == false`, `_allowedWhitelistIndex > 0`, buy where `from == _pool`.

## Short-window / manipulable TWAP in `peek` lets the per-address cap be bypassed (or griefed)
*(consensus, 3 of 6 reports)*
- Location: `hardhat-vultisig/contracts/oracles/uniswap/UniswapV3Oracle.sol` : `peek`; `hardhat-vultisig/contracts/Whitelist.sol` : `checkWhitelist`
- Mechanism: `peek` uses the TWAP over `min(30 min, getOldestObservationSecondsAgo(pool))` with no minimum observation age/cardinality/liquidity check. For a young or low-cardinality pool the window collapses to a short interval (with cardinality 1, `getOldestObservationSecondsAgo ≈ 0` and `consult` reverts `"BP"`, DoS'ing all gated buys). When short, a (e.g. flash-loan-funded) attacker can push the tick to under-price VULT, so `estimatedETHAmount` undercounts the buy and `_contributed[to]` stays below the real ETH value — letting a buyer exceed `_maxAddressCap`. The contract applies only a flat 5% cushion.
- Impact: An attacker can bypass the per-address ETH cap (or grief honest buyers into `MaxAddressCapOverflow`/`BP` reverts) by moving the pool price within a block or two — exactly the young-pool condition at launch.
- Reviewer disagreement: 1 of 6 (opus shot 1) defended this path, judging the 30-minute TWAP "reasonably manipulation-resistant."

## Permissionless `initProject` allows project squatting / admin hijack
*(consensus, 3 of 6 reports)*
- Location: `src/ILOManager.sol` : `initProject` / `_cacheProject`
- Mechanism: `initProject` is callable by anyone (`afterInitialize` only) and permanently caches a project keyed by the Uniswap pool, setting `admin = msg.sender`, with no proof the caller controls the sale token. A given `(saleToken, raiseToken, fee)` can be created only once (`require(_project.uniV3PoolAddress == address(0), "RE")`).
- Impact: A front-runner can preempt a real project's parameters, become the manager-recognized `admin`, force the legitimate team onto a different fee tier, and block them from launching ILO pools for that pool key.

## Minority findings

## Fee-on-transfer raise tokens inflate credited contributions
*(minority, 1 of 6 reports)*
- Location: `src/ILOPool.sol` : `buy`, `claimRefund`, `launch`
- Mechanism: `buy` credits `totalRaised` and `_positions[tokenId].raiseAmount` using the caller-supplied `raiseAmount`, then calls `safeTransferFrom` without measuring the actual balance delta received. Fee-on-transfer or otherwise non-standard raise tokens cause the pool to receive less than the credited amount.
- Impact: An attacker using such a token receives excess allocation/refund credit relative to funds actually received; `launch` may fail for insufficient raise-token balance, and during refunds early claimants can drain funds owed to later users.

## Whitelist cap systematically undercounts purchases via the 95% factor in `peek`
*(minority, 1 of 6 reports)*
- Location: `hardhat-vultisig/contracts/oracles/uniswap/UniswapV3Oracle.sol` : `peek`; `hardhat-vultisig/contracts/Whitelist.sol` : `checkWhitelist`
- Mechanism: `checkWhitelist` enforces `_maxAddressCap` using `IOracle(_oracle).peek(amount)`, but `peek` returns only 95% of the TWAP quote: `(quotedWETHAmount * baseAmount * 95) / 1e20`, systematically rounding the estimated ETH contribution down.
- Impact: A whitelisted buyer can exceed the intended per-address ETH cap by roughly 5.26% even with an honest TWAP, and by more if the TWAP diverges from execution price.

---

*Reconciliation: 12 distinct findings identified across the 6 input reports (by code path + root cause); 12 findings emitted (10 consensus, 2 minority). No findings dropped.*

