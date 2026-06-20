# Audit: 2025-06-panoptic

 ## 1. Performance fee rate is unbounded
- Location: `HypoVault.sol`: constructor, `executeWithdrawal`
- Mechanism: `performanceFeeBps` is stored as an immutable with no validation. In `executeWithdrawal` the fee is computed as `profit * performanceFeeBps / 10_000`. If the deployer sets `performanceFeeBps` above `10_000`, the fee can exceed the gross profit; for high enough values it exceeds `assetsToWithdraw`, causing `assetsToWithdraw -= performanceFee` to underflow and revert.
- Impact: A fee rate above 100% either confiscates principal on profitable withdrawals or permanently reverts them, locking user funds.

## 2. Withdrawals revert when feeWallet is unset
- Location: `HypoVault.sol`: constructor, `executeWithdrawal`
- Mechanism: `feeWallet` is never initialized in the constructor, so it defaults to `address(0)`. Whenever `executeWithdrawal` computes a positive `performanceFee`, it calls `SafeTransferLib.safeTransfer(underlyingToken, feeWallet, performanceFee)`. Transfers to the zero address revert in standard `SafeTransferLib` implementations, so the entire withdrawal transaction reverts.
- Impact: All profitable withdrawals are bricked until the owner sets a valid `feeWallet`. If the owner never does, those withdrawal proceeds remain locked.

## 3. Manager can drain the vault through arbitrary external calls
- Location: `HypoVault.sol`: `manage(address,bytes,uint256)` and `manage(address[],bytes[],uint256[])`
- Mechanism: The `manage` functions are `onlyManager` but impose no target whitelist, calldata restrictions, or value caps. They execute `target.functionCallWithValue(data, value)`, so the manager can call any contract on behalf of the vault, including calling `underlyingToken.approve(attacker, type(uint256).max)` and then pulling all vault tokens, or directly sending ETH to any address.
- Impact: A compromised or malicious manager (or an owner who instantly swaps the manager) can steal 100% of the vault’s ERC20 holdings and ETH.

## 4. Unsafe downcasts of sharesReceived and assetsReceived to uint128
- Location: `HypoVault.sol`: `fulfillDeposits`, `executeDeposit`, `fulfillWithdrawals`, `executeWithdrawal`
- Mechanism: `fulfillDeposits` computes `sharesReceived` as a `uint256`, adds the full amount to `totalSupply`, but stores `uint128(sharesReceived)` in `DepositEpochState.sharesReceived`. `fulfillWithdrawals` computes `assetsReceived` as a `uint256`, adds the full amount to `reservedWithdrawalAssets`, but stores `uint128(assetsReceived)` in `WithdrawalEpochState.assetsReceived`. Solidity silently truncates values that exceed `type(uint128).max`, and the execute functions later read those truncated values to mint shares and pay assets.
- Impact: Depositors can be minted fewer shares than the `totalSupply` increase, creating unbacked dead shares that dilute all holders. Withdrawers can be paid fewer assets than were reserved, leaving the residual permanently trapped in `reservedWithdrawalAssets`.

## 5. Total supply stays inflated for pending/unfulfilled withdrawals
- Location: `HypoVault.sol`: `requestWithdrawal`, `_burnVirtual`, `fulfillWithdrawals`
- Mechanism: `requestWithdrawal` calls `_burnVirtual`, which decrements the user’s `balanceOf` but does not decrement `totalSupply`. `fulfillWithdrawals` then subtracts only `sharesToFulfill` from `totalSupply`, leaving the unfulfilled portion of `sharesWithdrawn` in `totalSupply` even though no user currently holds those shares. The unfulfilled portion is merely carried as a `PendingWithdrawal` to the next epoch.
- Impact: `totalSupply` no longer equals the sum of user balances and is used as the pricing denominator for `fulfillDeposits` and `fulfillWithdrawals`. A manager can use partial withdrawal fulfillments to distort the effective share price, disadvantaging other depositors and withdrawers.

## 6. Accountant ignores net negative/debt exposure
- Location: `PanopticVaultAccountant.sol`: `computeNAV`
- Mechanism: For each pool the contract computes `poolExposure0 + poolExposure1` and adds only `uint256(Math.max(poolExposure0 + poolExposure1, 0))` to `nav`. Any pool with a net short or negative exposure is treated as zero rather than subtracting the liability.
- Impact: NAV can be overstated when the vault holds short options or net negative positions. Withdrawers can redeem shares at an inflated price, leaving the vault undercollateralized and causing losses for remaining shareholders.

## 7. NAV valuation relies on manager-supplied prices
- Location: `PanopticVaultAccountant.sol`: `computeNAV`
- Mechanism: Position token amounts and price conversions are computed using `managerPrices[i].poolPrice`, `managerPrices[i].token0Price`, and `managerPrices[i].token1Price`. These prices are only required to be within `maxPriceDeviation` of the corresponding TWAP; the contract does not mandate using the oracle TWAP itself. `maxPriceDeviation` and `twapWindow` are stored in the owner-controlled `PoolInfo` hash with no protocol-enforced sanity bounds.
- Impact: The manager can select any price within the configurable deviation band to inflate or deflate NAV. Since `fulfillDeposits` and `fulfillWithdrawals` price shares directly from NAV, this allows systematic value extraction from depositors and withdrawers.
