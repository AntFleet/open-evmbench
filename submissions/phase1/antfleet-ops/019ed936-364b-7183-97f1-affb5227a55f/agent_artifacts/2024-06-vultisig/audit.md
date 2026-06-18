# Audit: 2024-06-vultisig

I have both reports fully inline, so this is a synthesis/merge task — no code search needed. I cross-mapped every finding by root cause and code path.

Mapping summary:
- A.2 ↔ B.1 (initializer front-run) → consensus
- A.5 ↔ B.2 (per-user cap bypass) → consensus
- A.1 (fee-taker half) ↔ B.3 (fee-taker leak) → consensus
- A.1 (zero fee-growth / locking half) ↔ B.4 (pre-ILO fee-growth overcounting) → consensus
- A.3 ↔ B.5 (fees > 100% brick claims) → consensus
- A.4 (launch griefing), A's Whitelist/TWAP note, A's reentrancy note → Reviewer A only
- Report B has no findings absent from A.

Note: Report A bundled the two `claim()` defects (fee misallocation + zero-checkpoint overcounting) into one finding; Report B split them into B.3 and B.4. I preserve both as separate consensus findings to retain each report's specific detail.

---

# Merged Security Audit Report — ILO / Vultisig Contracts

## Consensus findings

## Initializer has no access control and is front-runnable
*(consensus)*
- Location: `src/ILOManager.sol` : `initialize(...)` (≈ lines 33-47) and the `constructor`.
- Mechanism: `initialize` is `external` and gated only by `whenNotInitialized()`; there is no `onlyOwner`/caller check. The constructor only does `transferOwnership(tx.origin)` and never calls `_disableInitialize()`, so `_initialized` is false after deployment. The first caller sets `FEE_TAKER`, `UNIV3_FACTORY`, `WETH9`, `ILO_POOL_IMPLEMENTATION`, the fee values, and calls `transferOwnership(initialOwner)`. The deploy scripts (`Deploy.s.sol`, `Init.s.sol`) deploy and initialize in separate transactions against a deterministic (precomputable) CREATE2 address, leaving a public window.
- Impact: An attacker who calls `initialize` before the intended deployer permanently takes ownership of the manager — setting `initialOwner` and `FEE_TAKER` to themselves and `ILO_POOL_IMPLEMENTATION` to a malicious clone target. They redirect all platform/performance fees, substitute the pool implementation used by every future project, and control project configuration. Full takeover of the deployment.

## Per-user cap bypassable via transferable position NFTs
*(consensus)*
- Location: `src/ILOPool.sol` : `buy(uint256 raiseAmount, address recipient)` (≈ lines 76-119) — the `balanceOf(recipient) == 0` branch, the `tokenOfOwnerByIndex(recipient, 0)` lookup, and `require(raiseAmount <= saleInfo.maxCapPerUser - _position.raiseAmount, "UC")`.
- Mechanism: Positions are freely transferable ERC-721 NFTs, but `buy` ties accounting to the recipient's first NFT (`tokenOfOwnerByIndex(recipient, 0)`) and enforces `maxCapPerUser` against only that single position's `raiseAmount`. If `balanceOf(recipient) == 0` a new NFT is minted with `raiseAmount` starting at zero. A whitelisted buyer can therefore buy up to `maxCapPerUser`, transfer the NFT away, then buy again to receive a fresh position with a fresh cap; conversely, if a recipient holds more than one NFT, purchases are steered onto whichever token sits at index 0 (possibly a transferred-in position with a different intended owner/schedule).
- Impact: A whitelisted attacker can exceed `maxCapPerUser` and consume an arbitrary portion of the pool hard cap (bounded only by total hard cap and available funds), defeating the fair-distribution control. Combined with whitelisting being checked on `recipient` (anyone may fund a buy for any whitelisted address), allocation controls are weaker than they appear.

## `claim()` sends other investors' accrued fees to the fee taker
*(consensus)*
- Location: `src/ILOPool.sol` : `claim(uint256 tokenId)` (≈ lines 122-186) — the `pool.burn` / `pool.collect(address(this), TICK_LOWER, TICK_UPPER, type(uint128).max, type(uint128).max)` block and the two `safeTransfer(..., feeTaker, amountCollected - amount)` lines.
- Mechanism: Every ILO NFT (each investor position plus every project-vest position created in `launch()`) is backed by one single Uniswap V3 position owned by the pool at the same `(TICK_LOWER, TICK_UPPER)`. `claim()` burns only the caller's `liquidity2Claim` but calls `pool.collect` with `type(uint128).max` amounts, draining all tokens owed to the shared aggregate position. Uniswap's `burn` pokes the entire position's accrued swap fees into `tokensOwed` (it uses `position.liquidity` before applying the delta), so the first claimer collects 100% of the pool's accrued fees. The caller's own share is computed, and the remainder `amountCollected - amount` is shipped to `FEE_TAKER` even though that excess includes fees accrued for every other NFT holder.
- Impact: The first claimant after fees accrue causes every other holder's accrued trading fees to be paid out to the fee taker. Later claimants lose those fees and receive less than their accrued entitlement. No special attacker is required — ordinary use misallocates fees.

## Zero-initialized per-position fee-growth checkpoints overcount fees, reverting and locking/draining funds
*(consensus)*
- Location: `src/ILOPool.sol` : `claim` (≈ lines 122-186), with checkpoints never set in `buy` (≈ lines 76-119) or the project-vest position minting inside `launch` (≈ lines 190-245). (Reviewer A reported this together with the fee-taker leak above.)
- Mechanism: Each position's `feeGrowthInside0LastX128` / `feeGrowthInside1LastX128` initialize to 0 and are never set in `buy()` or in the project-vest minting in `launch()`. At claim the per-position fee is computed as `fees = (feeGrowthInside - feeGrowthInside0LastX128) * positionLiquidity / Q128`, subtracting zero — so it is measured "since launch" (effectively since the pool/range genesis) while the actually-collected amount only contains fees accrued since the previous poke. If the Uniswap pool/range already had nonzero fee growth before the ILO liquidity was minted, the claim calculation includes fees from before the ILO position existed.
- Impact: On subsequent claims `amount` exceeds `amountCollected`, so `amountCollected0 - amount0` / `amountCollected1 - amount1` (Solidity 0.7.6, unchecked) wraps to a near-`uint256.max` value and the `safeTransfer` to `feeTaker` reverts with `ST` — permanently locking later claimants' vested liquidity and fees in the contract. For pre-existing or pre-manipulated pools/ranges, inflated claim amounts can also drain unrelated token balances held by the pool or otherwise break fee distribution.

## Unbounded `PLATFORM_FEE` / `PERFORMANCE_FEE` can brick claims
*(consensus)*
- Location: `src/ILOManager.sol` : `setPlatformFee(uint16)`, `setPerformanceFee(uint16)`, `_cacheProject` (≈ lines 130-138) and the initial values in `initialize`; consumed by `src/ILOPool.sol` : `_deductFees(uint256, uint256, uint16)` (≈ lines 312-323).
- Mechanism: `PLATFORM_FEE` and `PERFORMANCE_FEE` are `uint16` values with no upper-bound validation in either setter or in `initialize` (a `require(fee <= BPS /*10000*/)` is missing). Projects cache these fee values at creation (`_cacheProject`). `_deductFees` computes `amount0 - FullMath.mulDiv(amount0, feeBPS, BPS)` without checking `feeBPS <= 10000`; under Solidity 0.7.6 (unchecked), any `feeBPS > 10000` makes the subtrahend exceed `amount0` and the subtraction underflows/wraps.
- Impact: A misconfigured or malicious manager owner setting a fee above 100% (cached permanently into any project created afterward) causes every `claim()` (platform-fee path) and every fee settlement (performance-fee path) to compute nonsensical amounts and revert during token transfers — permanently freezing all affected positions. Even values `< 10000` but very large silently confiscate nearly all principal/fees to the fee taker.

---

## Additional findings (single-reviewer)

## `launch()` is permissionless and grief-able via the exact-price check
*(Reviewer A only)*
- Location: `src/ILOManager.sol` : `launch(address uniV3PoolAddress)`.
- Mechanism: `launch` has no caller restriction and requires `_cachedProject[...].initialPoolPriceX96 == sqrtPriceX96`, read live from `slot0()`. Before launch the Uniswap pool is only initialized (no ILO liquidity), so anyone can add a small amount of liquidity and execute a swap to move `slot0().sqrtPriceX96` off `initialPoolPriceX96`, after which the equality check fails for every `launch` attempt. The price equality is also the only protection guarding the launch math, which assumes the untouched initial price.
- Impact: An attacker can repeatedly nudge the pool price to block `launch()` until `refundDeadline` passes, after which `launch()` is forbidden and the project is forced into refund — a denial-of-service that prevents an otherwise-successful sale (soft cap met) from ever launching.

## Whitelist per-address cap depends on a biasable TWAP and only triggers on `from == _pool`
*(Reviewer A only)*
- Location: `Whitelist.sol` : `checkWhitelist`.
- Mechanism: `_maxAddressCap` is enforced using `IOracle.peek` (a 30-minute TWAP — hard but not impossible to bias) and only when the transfer originates directly from the configured pool (`from == _pool`). Token movements routed so that `from != _pool` (e.g. via a whitelisted intermediary contract that then forwards) skip the per-address ETH cap entirely.
- Impact: Determined buyers can exceed `_maxAddressCap` by routing transfers through an intermediary so the hook's cap check never fires, and the TWAP dependency leaves residual room to bias the cap. This is an inherent limitation of the hook-based cap rather than a clean single-call exploit.

## Missing reentrancy guard with arbitrary project-supplied ERC-20s (trust assumption)
*(Reviewer A only)*
- Location: `src/ILOPool.sol` : `claim` — external token transfers precede the `feeTaker` transfer; `token0`/`token1` are arbitrary project-supplied ERC-20s.
- Mechanism: Sale/raise tokens are arbitrary ERC-20s and there is no reentrancy guard. State (`position.liquidity`, fee growth) is updated before the transfers, and the time-window guards make `buy`/`claimRefund` cross-function reentry impractical, so no profitable reentrancy was identified — but a malicious token at `token0/token1` reentering during transfer is an unguarded trust assumption.
- Impact: No concrete profitable exploit found; flagged as a latent risk — a malicious or hookable token contract used as `token0`/`token1` could attempt reentrancy during `claim()`'s transfers, and the absence of a guard removes defense-in-depth.

