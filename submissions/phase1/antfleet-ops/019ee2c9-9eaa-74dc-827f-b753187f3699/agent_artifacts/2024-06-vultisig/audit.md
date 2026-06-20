# Audit: 2024-06-vultisig

## Unprotected initializer lets the first caller seize the manager
- Location: `src/ILOManager.sol` : `initialize`
- Mechanism: `initialize` is `external` and guarded only by `whenNotInitialized()`. The constructor does not mark the contract initialized, so if deployment and initialization are not atomic, any account can call `initialize` first and overwrite the live configuration: `owner`, `FEE_TAKER`, `ILO_POOL_IMPLEMENTATION`, `UNIV3_FACTORY`, `WETH9`, and fee parameters. This is a full initialization-takeover window.
- Impact: An attacker can take ownership of the manager, redirect protocol fees, point new sales at a malicious pool implementation, and control all future projects created through the contract.

## Claiming one NFT sweeps other investors’ fees to `FEE_TAKER`
- Location: `src/ILOPool.sol` : `claim`
- Mechanism: The contract tracks many user NFTs against one aggregate Uniswap V3 position. In `claim`, it burns only the claimant’s `liquidity2Claim`, but then calls `pool.collect(..., type(uint128).max, type(uint128).max)`, which collects all accrued fees for the aggregate position, including fees attributable to still-unclaimed NFTs. The function only credits the current claimant with their computed share, then sends the collected remainder to `FEE_TAKER` via `amountCollected0 - amount0` and `amountCollected1 - amount1`.
- Impact: Each successful claim confiscates fees owed to other investors and transfers them to the fee taker. Later claimants are underpaid, and their future claims can fail because the pool no longer holds the fees their per-position accounting expects.

## Refund rights can be front-run away after the refund deadline
- Location: `src/ILOManager.sol` : `launch`
- Mechanism: Investor refunds become available only through `ILOPool.refundable()` after `refundDeadline`, but `ILOManager.launch` never checks `refundDeadline`. Until someone actually triggers a refund and sets `_refundTriggered`, anyone can still call `launch` after the refund deadline and set `_launchSucceeded`, which permanently disables all refunds. Because `launch` is permissionless, a late launch can front-run refund transactions from the mempool.
- Impact: Once investors should be entitled to refunds, a project or third party can strip that right by racing a `launch`, forcing participants into the launched position instead of letting them recover their raise tokens.

## Public pool price manipulation can permanently DoS launch
- Location: `src/ILOManager.sol` : `initProject`, `launch`
- Mechanism: `initProject` creates and initializes the Uniswap V3 pool before the sale is launched. That pool is public, so any outsider can add small liquidity and move `slot0().sqrtPriceX96` away from the configured start price. Later, `launch` requires exact equality with `initialPoolPriceX96`; any deviation reverts. Because the equality check is exact and the pool state is attacker-mutable, launch can be griefed indefinitely.
- Impact: An attacker can block project launch at low cost by moving the pool price before each launch attempt, forcing the sale into a failed/refund path or leaving it stuck.

## Whitelist cap accounting underestimates every purchase
- Location: `hardhat-vultisig/contracts/oracles/uniswap/UniswapV3Oracle.sol` : `peek`
- Mechanism: The oracle comment says it “add[s] 5% slippage,” but the formula returns `(quotedWETHAmount * baseAmount * 95) / 1e20`, which discounts the quote by 5% instead of inflating it. `Whitelist.checkWhitelist` uses this value as `estimatedETHAmount` for `_contributed[to]` and for the `_maxAddressCap` check, so every buy is recorded below its intended ETH-equivalent amount.
- Impact: Buyers can exceed the intended per-address whitelist cap by about 5.26% even with accurate pricing, and potentially more when the TWAP lags, defeating the sale-allocation limit.

