# Audit: 2024-06-vultisig

I audited the bundled Vultisig token/whitelist contracts and the Krystal ILO contracts. The genuine security findings are below.

## Aggregate-position fee/principal misrouting in `claim` sends users' funds to the fee taker
- Location: `src/ILOPool.sol` : `claim`
- Mechanism: The ILOPool holds **one** Uniswap V3 position at `[TICK_LOWER, TICK_UPPER]`, but mints **many** NFTs (one per investor plus project vesting NFTs) that all share that single underlying position. In `claim`, after `pool.burn(...)` for the caller's `liquidity2Claim`, the code calls `pool.collect(address(this), TICK_LOWER, TICK_UPPER, type(uint128).max, type(uint128).max)`, which sweeps **all** tokens owed to the aggregate position (every other holder's already-burned principal and the entire pool's accrued fees). It then sends only this tokenId's computed `amount0/amount1` to the owner and forwards the entire remainder `amountCollected0 - amount0` / `amountCollected1 - amount1` to `FEE_TAKER`. Fees and principal that belong to other NFT positions are therefore routed to the fee taker rather than retained for those holders.
- Impact: The first claimer's transaction drains all currently-collectable fees of the whole position to the fee taker. Subsequent claimers compute large `fees0/fees1` from a feeGrowth delta whose tokens were already swept, so `amountCollected0 - amount0` underflows (revert) or the final `safeTransfer` fails for lack of balance — locking later investors out of their liquidity. An attacker (or the fee taker) can claim first to siphon other users' fees; honest users are DoSed.

## Position `feeGrowthInside*LastX128` is never initialized at mint
- Location: `src/ILOPool.sol` : `buy` / `launch` (Position creation)
- Mechanism: New `Position` structs created in `buy` and `launch` leave `feeGrowthInside0LastX128`/`feeGrowthInside1LastX128` at zero. In `claim`, fees are computed as `(currentFeeGrowthInside - position.feeGrowthInside0LastX128) * positionLiquidity / Q128`. Because the per-position checkpoint is 0 rather than the pool's feeGrowthInside at the time the liquidity was added, the first claim credits the holder with fee growth measured from genesis of the Uniswap position, not from when their share was deployed.
- Impact: Combined with the shared-position collect above, this inflates the fees attributed to whichever position claims, enabling over-withdrawal of fee tokens at the expense of other holders / the contract's solvency.

## `ILOManager.initialize` has no access control (initialization front-running)
- Location: `src/ILOManager.sol` : `initialize`
- Mechanism: `initialize` is guarded only by `whenNotInitialized()`; it performs no `onlyOwner`/`msg.sender` check before `transferOwnership(initialOwner)` and setting `FEE_TAKER`, `ILO_POOL_IMPLEMENTATION`, `UNIV3_FACTORY`, `WETH9`, and fees. The constructor sets the owner to `tx.origin`, but the privileged configuration is applied in `initialize`, which anyone can call first.
- Impact: An attacker who front-runs the legitimate `initialize` call becomes the owner and sets `ILO_POOL_IMPLEMENTATION` to a malicious clone target and `FEE_TAKER` to themselves. Every subsequently created ILO pool is then a malicious implementation, letting them steal raise funds / sale tokens across all projects.

## Permissionless price check in `launch` allows launch DoS via pool price manipulation
- Location: `src/ILOManager.sol` : `launch`
- Mechanism: `launch` requires `_cachedProject[pool].initialPoolPriceX96 == slot0.sqrtPriceX96`. Between `initProject` and `launch`, the pool exists but ILO liquidity has not yet been deployed. Anyone can add a small position and swap to move `slot0` off `initialPoolPriceX96`, after which `launch` permanently reverts on the price equality check (and an attacker can re-skew the price each time the project tries to restore it).
- Impact: A griefer can indefinitely block a project from launching. Because soft-cap funds are only refundable after `refundDeadline`, investor capital can be held hostage and the project forced into the refund path.

## `buy` reuses the first existing NFT and lets a non-buyer's deposit pad someone else's position
- Location: `src/ILOPool.sol` : `buy`
- Mechanism: When `balanceOf(recipient) != 0`, `buy` routes the new raise into `tokenOfOwnerByIndex(recipient, 0)` and increments that position. `buy` is callable by anyone with `recipient` arbitrary (the caller pays `RAISE_TOKEN` via `safeTransferFrom(msg.sender, ...)`), and per-user accounting (`maxCapPerUser`, vesting schedule) keys off the recipient's *first* token. If the recipient acquired an ILO NFT by transfer (these positions are transferable ERC-721s), a later `buy` mixes new raise/liquidity and the buyer's vesting schedule into a position whose schedule was set for a different original owner, corrupting `maxCapPerUser` enforcement and vest accounting for that tokenId.
- Impact: Per-user cap and vesting guarantees can be bypassed/confused by transferring positions and buying into them, and a third party can force additional raise/liquidity into a holder's existing position.

## Minor: `whenNotInitialized` does not block re-entrant double init on `ILOManager`
- Location: `src/base/Initializable.sol` : `whenNotInitialized`
- Mechanism: The modifier checks `require(!_initialized)` and only sets `_initialized = true` *after* the body executes. Any external call made inside an initializer body (none here today, but the pattern is fragile) would see `_initialized == false`. Not currently exploitable in `ILOManager.initialize`/`ILOPool.initialize` since their bodies make no re-entrant external calls, but the check-then-set-after ordering is unsafe and worth flagging given how much trusted state `initialize` writes.

The Uniswap math libraries (`FullMath`, `TickMath`, `OracleLibrary`, `SqrtPriceMathPartial`, `LiquidityAmounts`) and the `Vultisig`/`UniswapV3Oracle` contracts matched their canonical upstream behavior; I found no exploitable deviation there beyond the standard TWAP-manipulation caveat already mitigated by the 30‑minute period and 5% slippage buffer.

