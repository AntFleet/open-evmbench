# Audit: 2025-06-panoptic

# HypoVault Security Audit

Findings below are limited to genuine security issues in the provided code. Trusted-manager/owner centralization is noted only where it enables concrete harm beyond “the manager is powerful by design.”

---

## `requestDeposit` credits deposits before token transfer (reentrancy)

- **Location:** `src/HypoVault.sol` : `requestDeposit`
- **Mechanism:** The function updates `queuedDeposit` and `depositEpochState.assetsDeposited` before `SafeTransferLib.safeTransferFrom`. If `underlyingToken` is hookable (ERC777, ERC1363, or a malicious ERC20 that callbacks before balance updates), a reentrant call can inflate queued deposits and epoch totals without a matching transfer (or with a single transfer credited multiple times).
- **Impact:** An attacker can queue and later execute deposits for shares they did not fully pay for, diluting other shareholders and withdrawing value funded by honest depositors.

```solidity
queuedDeposit[msg.sender][currentEpoch] += assets;
depositEpochState[currentEpoch].assetsDeposited += assets;
SafeTransferLib.safeTransferFrom(underlyingToken, msg.sender, address(this), assets); // after state
```

---

## Epoch state stored as `uint128` truncates while `totalSupply` uses `uint256`

- **Location:** `src/HypoVault.sol` : `fulfillDeposits`, `fulfillWithdrawals`, `executeDeposit`, `executeWithdrawal`
- **Mechanism:** `fulfillDeposits` / `fulfillWithdrawals` increase/decrease `totalSupply` with full `uint256` precision, but persist `sharesReceived`, `assetsFulfilled`, `assetsReceived`, `sharesFulfilled`, etc. as `uint128`. `executeDeposit` and `executeWithdrawal` prorate user payouts from those truncated epoch fields. Above `2^128-1`, stored epoch data silently truncates while `totalSupply` does not.
- **Impact:** Users executing deposits/withdrawals receive less than their fair share; the gap remains as unassigned supply or stranded `reservedWithdrawalAssets`. Late executors can be denied withdrawals (`reservedWithdrawalAssets` underflow) or depositors permanently lose claimable shares—accounting break and fund loss at scale.

---

## `userBasis` / `PendingWithdrawal.basis` truncated to `uint128`

- **Location:** `src/HypoVault.sol` : `requestWithdrawal`, `executeWithdrawal`
- **Mechanism:** `userBasis` is `uint256`, but `PendingWithdrawal.basis` is `uint128`, and the code uses `uint128(pendingWithdrawal.basis + withdrawalBasis)` when queueing. Sums above `type(uint128).max` truncate on cast.
- **Impact:** Cost basis is understated, so `performanceFee` on profitable withdrawals is undercharged or skipped. An attacker with very large basis can avoid fees and extract excess underlying at the expense of `feeWallet` and remaining LPs.

---

## Negative pool exposure ignored in NAV (liabilities treated as zero)

- **Location:** `src/accountants/PanopticVaultAccountant.sol` : `computeNAV`
- **Mechanism:** Per-pool contribution is `nav += uint256(Math.max(poolExposure0 + poolExposure1, 0))`. Net negative exposure (underwater shorts, net liabilities) is floored to zero instead of reducing NAV.
- **Impact:** NAV is overstated whenever the vault has meaningful underwater Panoptic exposure. The manager can `fulfillWithdrawals` at an inflated rate, reserving and paying out more underlying than the vault is worth; remaining depositors and withdrawers who execute later absorb the loss (classic insolvency / bank-run).

```solidity
// debt in pools with negative exposure does not need to be paid back
nav += uint256(Math.max(poolExposure0 + poolExposure1, 0));
```

---

## Withdrawal fulfillment is not backed by on-chain liquidity checks

- **Location:** `src/HypoVault.sol` : `fulfillWithdrawals`, `executeWithdrawal`
- **Mechanism:** `fulfillWithdrawals` sets `reservedWithdrawalAssets` from accountant NAV math only—it does not liquidate positions via `manage()` or verify `IERC20(underlyingToken).balanceOf(address(this))`. `executeWithdrawal` then transfers underlying from the vault’s bare token balance.
- **Impact:** If NAV includes illiquid Panoptic collateral/positions but free underlying is low, withdrawers who execute first drain idle cash (including unfulfilled queued deposits sitting in the contract). Later `executeWithdrawal` calls revert or leave users unpaid while `reservedWithdrawalAssets` accounting claims liquidity exists—withdrawal DoS and unfair ordering loss for users who cannot race to execute.

---

## Manager-controlled oracle band allows NAV bias within `maxPriceDeviation`

- **Location:** `src/accountants/PanopticVaultAccountant.sol` : `computeNAV`; consumed by `src/HypoVault.sol` : `fulfillDeposits`, `fulfillWithdrawals`
- **Mechanism:** NAV depends on `managerPrices` in `managerInput`, only constrained by `abs(managerPrice - twap) <= maxPriceDeviation`. The manager chooses prices anywhere in that band and supplies the position list. There is no user-side slippage or independent price enforcement on fulfill.
- **Impact:** A malicious or compromised manager can systematically bias NAV up on `fulfillWithdrawals` (overpay withdrawers / drain vault) or down on `fulfillDeposits` (mint excessive shares to chosen depositors), shifting value between user classes within the deviation window. TWAP manipulation (e.g., short-window TWAP + thin liquidity) widens the exploitable band.

---

## Zero fulfillment epochs cause division-by-zero in user execution

- **Location:** `src/HypoVault.sol` : `fulfillDeposits`, `fulfillWithdrawals`, `executeDeposit`, `executeWithdrawal`
- **Mechanism:** `fulfillDeposits(0, …)` and `fulfillWithdrawals(0, …, …)` are allowed and advance epochs with `assetsFulfilled == 0` or `sharesFulfilled == 0`. `executeDeposit` divides by `_depositEpochState.assetsFulfilled`; `executeWithdrawal` divides by `_withdrawalEpochState.sharesWithdrawn` and `_withdrawalEpochState.sharesFulfilled`.
- **Impact:** A malicious manager can advance epochs with zero fulfillment and brick `executeDeposit` / `executeWithdrawal` for affected users (permanent DoS on claiming queued requests unless remainder rollover paths save them—and zero-fulfill paths still hit div-by-zero when totals are zero).

---

## Fee-on-transfer / deflationary underlying breaks deposit accounting

- **Location:** `src/HypoVault.sol` : `requestDeposit`, `fulfillDeposits`
- **Mechanism:** `requestDeposit` records the requested `assets` amount, not `balanceAfter - balanceBefore`. `fulfillDeposits` mints shares against `assetsToFulfill` assuming full amounts were received.
- **Impact:** With fee-on-transfer tokens, the vault receives less than recorded. Share liabilities exceed real assets → insolvency; last withdrawers/depositors cannot be fully paid.

---

## Performance fees sent to unset `feeWallet` (zero address)

- **Location:** `src/HypoVault.sol` : `executeWithdrawal`, `setFeeWallet`
- **Mechanism:** `feeWallet` is never set in the constructor. If `performanceFee > 0` and the owner has not called `setFeeWallet`, fees are transferred to `address(0)`.
- **Impact:** Performance fees are permanently lost/burned (depending on token behavior) instead of being collected—protocol revenue loss; for some tokens this may also cause unexpected revert behavior on withdrawal execution.

---

## `executeWithdrawal` reduces `reservedWithdrawalAssets` by gross assets before fee skim

- **Location:** `src/HypoVault.sol` : `executeWithdrawal`
- **Mechanism:** `reservedWithdrawalAssets -= assetsToWithdraw` uses the pre-fee gross amount, then `performanceFee` is deducted and sent to `feeWallet`. Reserved balance therefore tracks gross obligations while net token outflow is lower.
- **Impact:** Not a direct theft vector by itself (rounding favors the vault), but it leaves a growing dust balance in `reservedWithdrawalAssets` versus real liabilities. Combined with truncation/insolvency issues above, later executors can hit `reservedWithdrawalAssets` underflow reverts even when the vault still holds tokens—withdrawal griefing/DoS for tail users.

---

## `requestWithdrawal` lacks explicit balance check before basis proration

- **Location:** `src/HypoVault.sol` : `requestWithdrawal`
- **Mechanism:** `withdrawalBasis = (previousBasis * shares) / userBalance` runs before `_burnVirtual`. If `shares > userBalance`, `_burnVirtual` reverts on underflow; if `userBalance == 0` with nonzero `previousBasis` (invariant break from bugs elsewhere), division by zero reverts. This is mostly safe in isolation.
- **Impact:** Low severity alone, but if virtual mint/burn ever desyncs from `totalSupply` (e.g., uint128 truncation), basis math can divide by a wrong balance and mis-assign basis, corrupting performance-fee accounting.

---

### Centralization (informational, not counted as separate padded findings)

The manager can call `manage()` arbitrarily and control `managerInput` to the accountant. That trust model is explicit; the critical issues above are ways that **non-manager users** (or a manager exploiting oracle/accounting flaws) can extract value or brick users **through the documented public flows**, not merely “manager is admin.”

---

### Not reported (by design / out of scope per your criteria)

- Gas/style/multicall patterns  
- Permissionless `executeDeposit` / `executeWithdrawal` (beneficiary is always the queued user)  
- Owner replacing `accountant` / `manager` (pure admin trust)  
- Initial `totalSupply = 1_000_000` bootstrap (mitigates empty-vault inflation; `+1` in `totalAssets` is a deliberate floor when pending deposits ≈ NAV)

If you want, I can rank these by severity (Critical/High/Medium/Low) or map each to a concrete proof-of-concept scenario step-by-step.

