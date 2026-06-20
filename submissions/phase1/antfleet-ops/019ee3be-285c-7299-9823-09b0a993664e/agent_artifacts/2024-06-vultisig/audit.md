# Audit: 2024-06-vultisig

**## Inaccurate TWAP price from insufficient observations**
- Location: hardhat-vultisig/contracts/oracles/uniswap/UniswapV3Oracle.sol : peek (and getOldestObservationSecondsAgo)
- Mechanism: `peek` calls `getOldestObservationSecondsAgo` then `consult` with `period = min(PERIOD, longestPeriod)`. For a newly created/initialized Uniswap V3 pool (common in `ILOManager._initUniV3PoolIfNecessary`), `observationCardinality` starts at 1 and the single observation timestamp yields a `longestPeriod` of only a few seconds (or 0), so the returned tick is effectively spot price. The subsequent 5% slippage adjustment is then applied to this unreliable value before returning to `Whitelist.checkWhitelist`.
- Impact: An attacker can perform a large buy from the `_pool` that would normally be rejected by `MaxAddressCapOverflow`; the underestimated `estimatedETHAmount` allows the `_contributed[to]` check to pass, bypassing the intended per-address cap.

**## Missing validation allows zero-address / uninitialized oracle in whitelist path**
- Location: hardhat-vultisig/contracts/Whitelist.sol : checkWhitelist (via `IOracle(_oracle).peek`)
- Mechanism: `setOracle` and `setVultisig` are owner-only, but `checkWhitelist` (called from `VultisigWhitelisted._beforeTokenTransfer`) performs an external call to `_oracle` with no zero-address or interface-existence guard. If the owner never calls `setOracle` (or sets it to address(0)), the call reverts or, worse, a malicious contract at that address can return arbitrary values.
- Impact: Token transfers that should be gated by the whitelist logic either always revert (DoS) or can be made to return any ETH estimate, letting an attacker bypass `NotWhitelisted` / `MaxAddressCapOverflow` checks.

**## Refund/launch race allows double-spend of raise tokens**
- Location: src/ILOPool.sol : claimRefund (modifier `refundable`) and launch
- Mechanism: `claimRefund` (user path) and `claimProjectRefund` (manager path) both set `_refundTriggered = true` under the `refundable` modifier when `block.timestamp >= refundDeadline`. However, `launch` only checks `!_refundTriggered` once at the beginning; a subsequent `claimRefund` call from another investor after the first refund but before `launch` finishes can still succeed because `_refundTriggered` is only written, not re-checked atomically with the balance transfer.
- Impact: Attacker (or any whitelisted user) can drain the contract's `RAISE_TOKEN` balance via repeated `claimRefund` calls after the first refund, leaving the project with insufficient tokens when `launch` later tries to `addLiquidity`.

**## Investor position can be created for arbitrary recipient bypassing whitelist**
- Location: src/ILOPool.sol : buy
- Mechanism: `buy(raiseAmount, recipient)` only checks `_isWhitelisted(recipient)` (via `ILOWhitelist`). The check occurs before any state change, but the call is external and `recipient` is supplied by the caller; nothing prevents a whitelisted caller from specifying any `recipient` address (including a contract that later transfers the minted NFT).
- Impact: An attacker who controls a single whitelisted address can mint investor NFTs (and the associated vesting claims) on behalf of any address, effectively laundering allocation to blacklisted or non-whitelisted parties.

**## No reentrancy guard on external calls during buy/claim**
- Location: src/ILOPool.sol : buy (line calling `TransferHelper.safeTransferFrom`) and claim (calls to `pool.burn` + `pool.collect` + multiple `TransferHelper.safeTransfer`)
- Mechanism: Both functions perform external calls (`safeTransferFrom`, `burn`, `collect`, token transfers) with no `nonReentrant` modifier and while state (`totalRaised`, `_positions[tokenId].liquidity`, `_launchSucceeded`) is only partially updated.
- Impact: A malicious `RAISE_TOKEN` or `SALE_TOKEN` that re-enters `buy` or `claim` can manipulate `totalRaised`, double-count liquidity shares, or drain fees before the position accounting is finalized.
