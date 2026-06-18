# Audit: 2025-06-panoptic

# Merged Security Audit — HypoVault & PanopticVaultAccountant

This report reconciles two independent audits (Reviewer A = Claude, Reviewer B = Codex) of the same codebase. Findings the two reviewers describe in common appear first; findings raised by only one reviewer follow.

---

## Consensus findings

## Partial deposit carry-forward rounding desynchronizes queued assets from epoch accounting
*(consensus)*
- Location: `src/HypoVault.sol` : `fulfillDeposits` / `executeDeposit` (around lines 333–371 and 516–553)
- Mechanism: On a partial fulfillment, `fulfillDeposits` rolls only the aggregate remainder into the next epoch as `assetsDeposited - assetsToFulfill` (`depositEpochState[currentEpoch].assetsDeposited = uint128(assetsRemaining)`), while `executeDeposit` floors each user's fulfilled assets independently and rolls each user's own remainder forward (`queuedDeposit[user][epoch + 1] += uint128(assetsRemaining)`). Because each per-user fulfilled amount is floored, the per-user remainders do not sum to the aggregate remainder: `Σ queuedDeposit[user][epoch+1] ≥ depositEpochState[epoch+1].assetsDeposited`. An attacker can amplify this by splitting a deposit across many addresses so each account rounds to zero fulfilled while the epoch still records a positive fulfilled amount.
- Impact: After a partial fulfillment, later deposits are priced against an understated aggregate denominator, so users collectively mint slightly more shares than the `sharesReceived` added to `totalSupply` — the invariant `Σ balanceOf ≤ totalSupply` can be violated, diluting existing holders. With deliberate split-address dust the leak is maximized; the same drift can also make the last user's `cancelDeposit` underflow `depositEpochState.assetsDeposited -= uint128(queuedDepositAmount)` and revert. Preconditions: partial deposit fulfillment and amounts chosen to maximize rounding dust.

## Partial withdrawal carry-forward rounding desynchronizes queued shares and can misallocate reserved assets
*(consensus)*
- Location: `src/HypoVault.sol` : `fulfillWithdrawals` / `executeWithdrawal` (around lines 377–433 and 562–604)
- Mechanism: `fulfillWithdrawals` rolls the aggregate remainder as `sharesWithdrawn - sharesToFulfill`, but `executeWithdrawal` floors `sharesToFulfill` per user and rolls each user's individual remainder forward, so the summed user remainders can exceed `withdrawalEpochState[epoch + 1].sharesWithdrawn` (the same flooring/aggregation mismatch as the deposit path). Additionally, `executeWithdrawal` computes `withdrawnBasis` from the aggregate fulfillment ratio rather than from the actually fulfilled `sharesToFulfill`, so a user's basis can be consumed even when that user receives zero assets.
- Impact: Reserved assets and queued shares become inconsistent across epochs. If share value changes between epochs, early executors can consume assets that should be reserved for other withdrawers, leaving later users underpaid or reverted; users can also be overcharged performance fees because basis is discarded without a matching withdrawal payout. As with deposits, this can push `Σ balances` out of line with `totalSupply` and cause an underflow revert for the last canceller/claimant of an epoch. Preconditions: partial withdrawal fulfillment with rounding dust, especially many small withdrawal requests.

---

## Additional findings (single-reviewer)

## Silent `uint128` truncation of `sharesReceived` in `fulfillDeposits` inflates `totalSupply` vs. claimable shares
*(Reviewer A only)*
- Location: `HypoVault.sol` : `fulfillDeposits` (the `depositEpochState[currentEpoch] = DepositEpochState({... sharesReceived: uint128(sharesReceived) ...})` write, the `totalSupply = _totalSupply + sharesReceived` line, and the `emit DepositsFulfilled(..., sharesReceived)` line)
- Mechanism: `sharesReceived` is a full `uint256` (`Math.mulDiv(assetsToFulfill, _totalSupply, totalAssets)`). It is written into the epoch struct as an unchecked `uint128(sharesReceived)` cast, but `totalSupply` is incremented by the full `uint256` value and the event also emits the full value. `executeDeposit` later mints each user shares prorated from the *truncated* `depositEpochState.sharesReceived`. If `sharesReceived > 2^128 − 1`, the sum of all minted shares is far smaller than the amount added to `totalSupply`. Reachability is driven by the `totalSupply = 1_000_000` virtual offset: when `totalAssets` is small, `sharesReceived ≈ assetsToFulfill × totalSupply / totalAssets` explodes (at the first fulfilled deposit `totalAssets ≈ 1`, so `sharesReceived ≈ assetsToFulfill × 1e6`), and a large first deposit or a low-decimal/high-supply underlying pushes it past `2^128`. The same condition recurs whenever NAV collapses toward the floor and a deposit is fulfilled against a tiny `totalAssets`.
- Impact: Permanent, irrecoverable share/supply desync. The overflowed depositor loses the bulk of the shares they paid for, and all existing holders are silently diluted because `totalSupply` over-counts shares no user can ever claim; the emitted event disagrees with stored state. No party can repair the gap.

## Silent `uint128` truncation of `assetsReceived` in `fulfillWithdrawals` desyncs `reservedWithdrawalAssets`
*(Reviewer A only)*
- Location: `HypoVault.sol` : `fulfillWithdrawals` (the `withdrawalEpochState[currentEpoch] = WithdrawalEpochState({... assetsReceived: uint128(assetsReceived) ...})` write vs. `reservedWithdrawalAssets = _reservedWithdrawalAssets + assetsReceived`); related cast in `requestWithdrawal` (`uint128(pendingWithdrawal.basis + withdrawalBasis)`)
- Mechanism: `assetsReceived` (`uint256`) is stored as `uint128(assetsReceived)`, but `reservedWithdrawalAssets` is incremented by the full `uint256` and the event emits the full value. `executeWithdrawal` computes payouts from the *truncated* `withdrawalEpochState.assetsReceived` (`Math.mulDiv(sharesToFulfill, _withdrawalEpochState.assetsReceived, sharesFulfilled)`) while decrementing the reserve by those truncated-basis payouts. If `assetsReceived > 2^128 − 1`, the reserve is credited far more than will ever be paid, so `reservedWithdrawalAssets` permanently over-counts; that stale reserve is subtracted from `totalAssets` in every later `fulfillDeposits`/`fulfillWithdrawals`. The companion `requestWithdrawal` cast truncates a cumulative `userBasis` exceeding `2^128`, inflating computed profit and overcharging the performance fee.
- Impact: Permanent over-statement of reserved assets, depressed NAV/share price for remaining users, and stranded underlying. Lower practical reachability than the `sharesReceived` case (requires the vault to actually hold >`2^128` wei, plausible only for low-decimal/astronomically-supplied tokens), but it is the same unchecked-downcast class and should be fixed with the same safe cast.

## `feeWallet` is never initialized — profitable withdrawals send the performance fee to `address(0)`
*(Reviewer A only)*
- Location: `HypoVault.sol` : `constructor` (never sets `feeWallet`) and `executeWithdrawal` (`SafeTransferLib.safeTransfer(underlyingToken, feeWallet, performanceFee)`)
- Mechanism: The constructor sets `manager`, `accountant`, `performanceFeeBps`, and `totalSupply`, but leaves `feeWallet` at its default `address(0)`. Once `performanceFeeBps > 0` and a withdrawal is profitable, `executeWithdrawal` computes `performanceFee > 0` and calls `safeTransfer(underlyingToken, address(0), performanceFee)`. For any underlying that reverts on transfer-to-zero (e.g. OpenZeppelin ERC-20), the entire `executeWithdrawal` reverts; for a burn-tolerant token the fee is silently destroyed. `setFeeWallet` also performs no zero-address validation, so the broken state is the default rather than a guarded exception.
- Impact: Denial-of-service on every profitable withdrawal from genesis until the owner calls `setFeeWallet` (funds recoverable, liveness impact), or permanent loss of accrued fees for burn-tolerant tokens. A first-class initialization bug.

## Zero-amount epoch fulfillment permanently bricks `executeDeposit` / `executeWithdrawal` for that epoch (division by zero)
*(Reviewer A only)*
- Location: `HypoVault.sol` : `executeDeposit` (`Math.mulDiv(userAssetsDeposited, _depositEpochState.sharesReceived, _depositEpochState.assetsFulfilled)`) and `executeWithdrawal` (`Math.mulDiv(sharesToFulfill, _withdrawalEpochState.assetsReceived, _withdrawalEpochState.sharesFulfilled)`), reached from `fulfillDeposits`/`fulfillWithdrawals` which advance the epoch even when the fulfilled amount is `0`
- Mechanism: `fulfillDeposits(0, …)` increments `depositEpoch` and records `assetsFulfilled = 0` for the closed epoch; symmetrically `fulfillWithdrawals(0, …)` records `sharesFulfilled = 0`. When a user later calls `executeDeposit`/`executeWithdrawal`, the `Math.mulDiv` denominator is `0` and reverts. Because the call reverts, the user can neither claim nor reach the carry-forward branch that moves the unfulfilled remainder to `epoch + 1`. There is no recovery path: `cancelDeposit`/`cancelWithdrawal` only act on the *current* epoch, never on the stranded historical epoch, and for withdrawals the shares were already burned in `requestWithdrawal`.
- Impact: Any epoch the manager advances with zero fulfillment permanently locks every deposit queued in it (assets stuck) and every withdrawal queued in it (shares already burned → assets unrecoverable). Triggered by a single innocuous-looking manager action (e.g. `fulfillDeposits(0,…)` to "roll" an epoch), with no admin override to undo it.

## Manager-supplied option prices (bounded only by `maxPriceDeviation`) can bias reported NAV
*(Reviewer A only)*
- Location: `PanopticVaultAccountant.sol` : `computeNAV` — the `getAmountsForLiquidity(managerPrices[i].poolPrice, …)` call vs. the token0/token1→underlying conversion blocks that use the TWAP tick directly
- Mechanism: `managerPrices` and `tokenIds` are not part of the owner-locked `vaultPools` hash; only `pools` is. The manager may therefore supply any `poolPrice` within `±maxPriceDeviation` of `twapFilter(poolOracle, twapWindow)`, and that price is fed straight into `Math.getAmountsForLiquidity` for every position leg, while the underlying conversions use the raw TWAP. Combined with `computeNAV` reading spot `token.balanceOf(vault)` and `collateralToken.previewRedeem(...)`, the manager has a bounded band to bias NAV up or down at the exact moment deposits/withdrawals are fulfilled. This is gated behind `onlyManager` and the manager is already trusted via `manage()`, so it is not independently exploitable by an outsider — but the deviation band is the only protection against manager mispricing, and the spot-price-for-legs / TWAP-for-conversion inconsistency widens it.
- Impact: Within `maxPriceDeviation`, the manager can move NAV to mint cheap shares, overpay withdrawals, or inflate performance fees. Bounded and trust-dependent rather than a permissionless exploit; surfaced so `maxPriceDeviation`, `twapWindow`, and `vaultLocked` are treated as security-critical configuration.

## Duplicate position IDs can spoof Panoptic NAV
*(Reviewer B only)*
- Location: `src/accountants/PanopticVaultAccountant.sol` : `computeNAV` (position-list validation around lines 119–153)
- Mechanism: The accountant checks that each supplied `tokenId` has a nonzero balance and that the total counted legs equals `pool.numberOfLegs(vault)`, but it does not enforce uniqueness or prove that the supplied list is the exact vault position set. A crafted list can duplicate a favorable position and omit an unfavorable position with the same leg count while still passing the `numLegs == numberOfLegs` check.
- Impact: A manager (or compromised manager) can overstate or understate NAV despite the intended position-list check, causing deposits or withdrawals to settle at manipulated prices and transferring value between depositors, withdrawers, and existing shareholders.

