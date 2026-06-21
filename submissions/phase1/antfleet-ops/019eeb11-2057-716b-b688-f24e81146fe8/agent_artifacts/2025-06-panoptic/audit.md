# Audit: 2025-06-panoptic
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Deposit fulfillment truncates minted shares to uint128
*(consensus, 5 of 6 reports)*
- Location: `src/HypoVault.sol` : `fulfillDeposits` (and the distribution in `executeDeposit`)
- Mechanism: `sharesReceived = Math.mulDiv(assetsToFulfill, _totalSupply, totalAssets)` is a `uint256`; `totalSupply` is incremented by the full value and the event emits the full value, but it is stored into `DepositEpochState.sharesReceived` via a narrowing `uint128(sharesReceived)` cast. `executeDeposit` distributes shares from the truncated stored figure. Reachable on the *first* fulfillment, because `totalAssets = NAV + 1 − assetsDeposited − reservedWithdrawalAssets` collapses to `1`, so `sharesReceived = assetsToFulfill * 1_000_000` and a deposit of ~3.4e32 base units overflows `uint128`.
- Impact: Once `sharesReceived > type(uint128).max`, depositors collectively receive only the low 128 bits while `totalSupply` is inflated by the full amount — unbacked phantom supply that dilutes every holder and effectively confiscates the depositors' assets; the emitted event disagrees with stored state.

## Withdrawal fulfillment truncates assets owed to uint128
*(consensus, 5 of 6 reports)*
- Location: `src/HypoVault.sol` : `fulfillWithdrawals` (and the payout in `executeWithdrawal`)
- Mechanism: `assetsReceived = Math.mulDiv(sharesToFulfill, totalAssets, _totalSupply)` is a `uint256`; `reservedWithdrawalAssets` is incremented by the full value and the event emits the full value, but it is stored as `uint128(assetsReceived)`. `executeWithdrawal` pays each user from the truncated value and decrements `reservedWithdrawalAssets` by that small amount.
- Impact: When `assetsReceived > type(uint128).max`, withdrawers are paid a truncated fraction (principal loss) while `reservedWithdrawalAssets` is left permanently overstated. Because `totalAssets = computeNAV + 1 − assetsDeposited − reservedWithdrawalAssets`, the inflated reserve understates NAV for everyone and can underflow/revert, bricking all future deposit and withdrawal fulfillments.

## Zero-asset deposit fulfillment permanently locks queued deposits (division by zero)
*(consensus, 3 of 6 reports)*
- Location: `src/HypoVault.sol` : `executeDeposit` (`Math.mulDiv(userAssetsDeposited, sharesReceived, assetsFulfilled)`), triggered by `fulfillDeposits(0, …)`
- Mechanism: `fulfillDeposits` accepts `assetsToFulfill == 0`, writing `assetsFulfilled = 0` and `sharesReceived = 0` for the epoch, advancing `depositEpoch` and rolling the aggregate forward — but each user's `queuedDeposit[user][N]` is only migrated inside `executeDeposit`, which then computes `Math.mulDiv(userAssetsDeposited, 0, 0)` → division by zero → permanent revert. `cancelDeposit` only acts on the current epoch, so a past zero-fulfilled epoch can never be refunded or advanced.
- Impact: A single `fulfillDeposits(0, …)` call permanently locks every depositor's funds in that epoch with no admin escape hatch — an easily-hit footgun for an honest manager and a selective-bricking tool for a malicious one.

## Zero-share withdrawal fulfillment permanently destroys withdrawn shares (division by zero)
*(consensus, 3 of 6 reports)*
- Location: `src/HypoVault.sol` : `executeWithdrawal` (`Math.mulDiv(sharesToFulfill, assetsReceived, sharesFulfilled)`), triggered by `fulfillWithdrawals(0, …)`
- Mechanism: Symmetric to the deposit case, and worse because `requestWithdrawal` `_burnVirtual`s the user's shares up front. `fulfillWithdrawals` accepts `sharesToFulfill == 0` → `sharesFulfilled == 0`; `executeWithdrawal` then divides by zero and reverts forever. `cancelWithdrawal` only re-mints for the current epoch.
- Impact: One `fulfillWithdrawals(0, …)` call strips every withdrawer in that epoch of their (already-burned) shares with no way to redeem for assets and no way to restore the shares; the supply stays stranded in `totalSupply`. Irreversible user-fund loss from a single ordinary-looking manager call.

## Cost-basis (and queued amount) uint128 truncation in withdrawal accounting
*(consensus, 3 of 6 reports)*
- Location: `src/HypoVault.sol` : `requestWithdrawal` (`basis: uint128(pendingWithdrawal.basis + withdrawalBasis)`) and the `executeWithdrawal` rollover write (`queuedWithdrawal[user][epoch+1]` `amount`/`basis` uint128 casts)
- Mechanism: `userBasis` is a `uint256` and is decremented by the full `uint256` `withdrawalBasis`, but `PendingWithdrawal.basis`/`.amount` are `uint128` and the casts truncate silently with no range check. If accumulated basis (or the rolled-forward sums) exceeds `type(uint128).max`, stored basis is truncated downward while `userBasis` was reduced by the full amount — basis is destroyed, not conserved.
- Impact: `performanceFee = max(0, assetsToWithdraw − withdrawnBasis) * performanceFeeBps`; a too-small truncated basis makes the user pay performance fees on phantom "profit" that was actually returned principal, overpaying the fee wallet. The companion `amount` truncation can drop a user's queued shares on rollover.

## Deposits credited gross without verifying received balance (fee-on-transfer)
*(consensus, 3 of 6 reports)*
- Location: `src/HypoVault.sol` : `requestDeposit`
- Mechanism: `queuedDeposit` and `depositEpochState.assetsDeposited` are incremented by the user-supplied `assets` before `safeTransferFrom`, and the vault never checks the actual balance delta received. Fee-on-transfer, deflationary, or rebasing underlying tokens deliver less than `assets` while the vault books the full amount.
- Impact: A depositor is over-credited relative to assets delivered, shifting transfer-tax/rebase losses onto existing shareholders; in thin epochs it can force `fulfillDeposits`/`cancelDeposit` to subsidize from existing vault assets or underflow and brick.

## Performance fees avoidable by splitting withdrawals (per-execution rounding)
*(consensus, 2 of 6 reports)*
- Location: `src/HypoVault.sol` : `executeWithdrawal`
- Mechanism: `performanceFee = profit * performanceFeeBps / 10_000` is computed independently per executed withdrawal and rounded down each time. Shares are transferable and withdrawals are accounted per user/epoch, so a profitable holder can split shares across many addresses or small requests so each per-withdrawal fee rounds to zero.
- Impact: A profitable withdrawer can reduce or fully avoid performance fees (loss borne by `feeWallet`). Feasibility depends on token decimals, share granularity, `performanceFeeBps`, and gas.

## Accountant position-list bypassable with duplicate TokenIds
*(consensus, 2 of 6 reports)*
- Location: `src/accountants/PanopticVaultAccountant.sol` : `computeNAV`
- Mechanism: The manager-supplied `tokenIds` list is validated only by each entry having a nonzero balance and by `sum(countLegs()) == pool.numberOfLegs(_vault)`. There is no uniqueness check and no check that the list equals the actual open positions. A duplicated position (nonzero balance) can replace an omitted different position with the same total leg count; the duplicate is double-counted and the omitted one dropped.
- Impact: The manager can over- or understate NAV by swapping a high-value position for a duplicate of another, then mint cheap shares to themselves (deflated NAV) or over-pay their own withdrawals (inflated NAV), extracting value from other vault users.
- Reviewer disagreement: 2 reports (opus shots 2 and 3) defended this path, arguing the `numberOfLegs` completeness check plus the owner-locked pools hash and `maxPriceDeviation` bounds constrain NAV manipulation.

## Per-user deposit rollover rounding desync creates phantom deposits
*(consensus, 2 of 6 reports)*
- Location: `src/HypoVault.sol` : `fulfillDeposits` / `executeDeposit`
- Mechanism: `fulfillDeposits` rolls the aggregate next-epoch amount as `assetsDeposited − assetsToFulfill`, but `executeDeposit` rolls each user's remainder as `queuedDepositAmount − floor(queuedDepositAmount * assetsFulfilled / assetsDeposited)`. The sum of per-user rounded-down remainders can exceed the aggregate remainder, especially with deposits split across many accounts.
- Impact: An attacker splits deposits so a partial fulfillment rounds each account's fulfilled assets toward zero, then rolls more user-level deposit claims into the next epoch than the aggregate `assetsDeposited` records — minting shares for phantom assets, breaking `totalSupply` vs `balanceOf`, and transferring value between depositors and shareholders if NAV moves between epochs.
- Reviewer disagreement: opus shots 1 and 2 defended the cross-epoch carry-forward as internally consistent with the aggregate remainder and rounding uniformly down in the vault's favor.

## Per-user withdrawal rollover rounding desync enables cross-epoch repricing
*(consensus, 2 of 6 reports)*
- Location: `src/HypoVault.sol` : `fulfillWithdrawals` / `executeWithdrawal`
- Mechanism: `fulfillWithdrawals` rolls the aggregate next-epoch shares as `sharesWithdrawn − sharesToFulfill`, but `executeWithdrawal` rolls each user's remainder as `pending.amount − floor(pending.amount * sharesFulfilled / sharesWithdrawn)`. Splitting withdrawals can make many users' fulfilled shares round to zero while aggregate assets are already reserved and supply already reduced, pushing full individual claims into the next epoch without matching aggregate state.
- Impact: A withdrawer can defer already-reserved fulfilled shares into a later epoch and have them paid at the later epoch's price; if NAV rises or is manipulated first, they extract more than their original pro-rata value, leaving other withdrawers underpaid or reverting on `reservedWithdrawalAssets` underflow.
- Reviewer disagreement: opus shots 1 and 2 defended the carry-forward as consistent with the aggregate remainder and rounding-down in the vault's favor.

## Minority findings

## Direct balance donation manipulates deposit pricing
*(minority, 1 of 6 reports)* *(conflicting reviews: 2 of 6 reports defended this code path)*
- Location: `src/HypoVault.sol` : `fulfillDeposits`; `src/accountants/PanopticVaultAccountant.sol` : `computeNAV`
- Mechanism: Deposit share pricing uses `accountant.computeNAV(...) + 1 − epochState.assetsDeposited − reservedWithdrawalAssets`, and `computeNAV` includes direct vault token balances via `balanceOf`, so unqueued token transfers into the vault raise NAV without being treated as deposits. There is also no depositor-specified minimum-shares check.
- Impact: An existing shareholder donates assets immediately before a deposit fulfillment to raise the share price for queued depositors; a large enough donation makes victim deposits mint very few or zero shares, transferring the queued deposit value to existing shareholders on later withdrawal.
- Reviewer disagreement: opus shots 1 and 2 defended this path, arguing the `1_000_000` virtual-share seed plus the `+1` virtual asset force a donation attack to require ~`2e6×` the victim's deposit, mitigating first-depositor/donation inflation.

## feeWallet never initialized and setter accepts zero
*(minority, 1 of 6 reports)*
- Location: `src/HypoVault.sol` : `constructor` / `setFeeWallet` (manifested in `executeWithdrawal`'s `SafeTransferLib.safeTransfer(underlyingToken, feeWallet, performanceFee)`)
- Mechanism: `feeWallet` defaults to `address(0)` and the constructor never sets it, while `performanceFeeBps` is an immutable that may be nonzero. The first profitable withdrawal triggers `safeTransfer(underlyingToken, address(0), performanceFee)`; standard ERC-20s revert on transfer to the zero address, so `executeWithdrawal` reverts. `setFeeWallet` performs no zero-address validation, so the state can be reintroduced post-deployment.
- Impact: Any withdrawal that accrued a performance fee cannot be claimed until the owner sets a valid `feeWallet`; since the shares were already burned and the assets already reserved, affected withdrawers are stuck (assets reserved, shares gone, claim reverting). If the token instead allows transfers to `0x0`, the fee is silently burned. Recoverable by the owner but an availability/initialization defect on the normal happy path.

---

*Reconciliation: 12 distinct findings identified across the 6 input reports (by code path + root cause); 12 findings emitted (10 consensus, 2 minority). No findings dropped. Deposit/withdrawal variants of the truncation, zero-fulfillment, and rollover-rounding classes are kept as separate entries because they live in distinct functions and touch distinct state, even where a single report combined them.*

