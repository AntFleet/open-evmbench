# Audit: 2025-01-liquid-ron

# Security Audit Report — LiquidRon / Escrow / LiquidProxy

Findings below are limited to exploitable or materially unsafe logic. Centralization risks (owner pause, fee changes) are noted only where they create a concrete user-fund path.

---

## ERC4626 inflation / first-depositor share theft
- **Location:** `LiquidRon.sol` : `deposit`, `mint`, `withdraw`, `redeem` (inherited ERC4626 accounting via `totalAssets()`)
- **Mechanism:** `totalAssets()` is `IERC20(asset()).balanceOf(this) + getTotalStaked() + getTotalRewards()`. A user can increase the vault’s WRON balance with a direct `transfer` to the vault (no shares minted). On a low-`totalSupply` vault, the classic ERC4626 inflation attack applies: attacker mints minimal shares, donates a large WRON balance to the vault, then the next depositor’s `convertToShares` rounds down to 0 (or near-zero) shares while their WRON is pulled in via the normal deposit path. `LiquidRon` does not override `_decimalsOffset()` / virtual-asset mitigations on the main ERC4626 path (only epoch redemption uses `+1` virtual assets in `_convertToAssets`).
- **Impact:** An attacker can steal most or all of the next victim’s deposit. Critical on early/low-liquidity deployments.

---

## Instant exit can fail while `totalAssets()` implies full redeemability
- **Location:** `LiquidRon.sol` : `withdraw`, `redeem`, `totalAssets`
- **Mechanism:** Share conversion uses `totalAssets()` (liquid WRON + staked + pending rewards). Payout uses `_withdrawRONTo`, which requires **liquid WRON** in the vault. Most value can be illiquid (delegated via proxies). `maxWithdraw` / `maxRedeem` (ERC4626 defaults) are not capped by on-hand liquidity.
- **Mechanism detail:** `super.withdraw` / `super.redeem` burn shares and move WRON to `address(this)`, then native RON is sent out. If liquid WRON < converted assets, the internal `safeTransfer` reverts even though pricing assumed staked funds back the shares.
- **Impact:** Not direct theft, but integrators/users relying on ERC4626 previews can plan exits that revert; in stress scenarios this creates a liveness / bank-run dynamic where only early leavers with small enough requests succeed. Misleading `maxWithdraw` can cause failed automation and stuck UX.

---

## Withdrawal-queue shares can be frozen indefinitely (no cancel, operator-gated finalization)
- **Location:** `LiquidRon.sol` : `requestWithdrawal`, `finaliseRonRewardsForEpoch`, `redeem(uint256)`
- **Mechanism:** `requestWithdrawal` irreversibly transfers user shares to the vault (`_transfer(msg.sender, address(this), _shares)`) with no cancel/unlock path. Claiming requires (1) `finaliseRonRewardsForEpoch` (only `onlyOperator`) and (2) `redeem(_epoch)` after `FINALISED`. If the operator never finalizes, or the contract stays paused (`finaliseRonRewardsForEpoch` is `whenNotPaused`), users cannot get shares back and cannot complete the queued exit.
- **Impact:** Malicious, compromised, or inactive operator can indefinitely freeze withdrawing users’ economic value (shares sit in the vault, user wallets empty of LRON). This is a concrete fund-access denial path, not just “trust owner” abstraction.

---

## Epoch withdrawal price is manipulable by operator at finalization time
- **Location:** `LiquidRon.sol` : `finaliseRonRewardsForEpoch`, `harvest`, `harvestAndDelegateRewards`
- **Mechanism:** Locked payout is `previewRedeem(lockedShares)` at finalization time, not at request time. Between `requestWithdrawal` and `finaliseRonRewardsForEpoch`, the operator can call `harvest` / `delegateAmount` / `undelegateAmount` (when unpaused) to change `totalAssets()` and thus the locked `assetSupply` for that epoch.
- **Impact:** Operator can systematically favor or harm queued withdrawers (e.g., harvest before finalize to increase their payout; delay harvest to reduce it). Queued users bear oracle/operator timing risk beyond normal liquid-staking slippage.

---

## `undelegateAmount` assumes immediate native RON availability (Ronin unbonding mismatch)
- **Location:** `LiquidProxy.sol` : `undelegateAmount`; `LiquidRon.sol` : `undelegateAmount` (caller)
- **Mechanism:** After `bulkUndelegate`, the proxy immediately calls `_depositRONTo(vault, totalUndelegated)` for the **full requested amounts**. On Ronin-style staking, undelegation is typically **not** instantly liquid; RON is released only after an unbonding period. If the staking contract does not credit the proxy synchronously, the call either reverts (DoS on undelegation) or, worse, if partial/native balance is lower than `totalUndelegated`, `_depositRONTo` reverts after undelegation already executed on-chain.
- **Impact:** Broken undelegation liveness and potential desync between `getTotalStaked()` (already reduced on-chain) and vault liquidity if any partial/async path exists. Operators may be unable to free stake to honor withdrawals; accounting can diverge from economic reality during unbonding.

---

## `LiquidProxy.harvest` sweeps the proxy’s entire native balance
- **Location:** `LiquidProxy.sol` : `harvest`
- **Mechanism:** Rewards are measured as `address(this).balance` after `claimRewards`, not as a delta from a pre-claim snapshot. The proxy’s `receive()` is intentionally open. Any native RON sitting on the proxy (unbonding proceeds, accidental transfers, timing leftovers between delegate/undelegate and accounting) is wrapped and sent to the vault on harvest.
- **Impact:** Usually donates stray funds to the vault, but if RON on the proxy was intended to remain temporarily unaccounted (e.g., awaiting a separate operator action), it is force-moved into vault NAV and included in share pricing without explicit reconciliation. Can cause premature NAV recognition of funds not yet economically available to honor withdrawals.

---

## `harvest` may repeatedly call `claimRewards` on the full validator array
- **Location:** `LiquidProxy.sol` : `harvest`
- **Mechanism:** The loop is:
  ```solidity
  for (uint256 i = 0; i < _consensusAddrs.length; i++) {
      IRoninValidator(roninStaking).claimRewards(_consensusAddrs);
  }
  ```
  Each iteration passes the **entire** `_consensusAddrs` array, not a single index. Behavior depends entirely on Ronin’s `claimRewards` implementation (duplicate claims, reverts, or griefing gas blow-up).
- **Impact:** If `claimRewards` is not strictly idempotent, this can revert harvest (reward denial) or produce unexpected accounting. Operator-controlled, but a real logic error in the claim path that affects user yield.

---

## `redelegateAmount` validates inputs after the external redelegation call
- **Location:** `LiquidRon.sol` : `redelegateAmount`
- **Mechanism:** `ILiquidProxy(...).redelegateAmount(...)` is invoked **before** the zero-amount check and `_tryPushValidator` on destinations. A call with `_amounts[i] == 0` still hits the staking contract first.
- **Impact:** Operator can accidentally execute unintended redelegations with zero amounts (behavior depends on Ronin staking). Validation-after-interaction pattern risks state changes that were meant to be blocked.

---

## Missing array-length validation on batched staking operations
- **Location:** `LiquidProxy.sol` : `delegateAmount`, `redelegateAmount`, `undelegateAmount`; `LiquidRon.sol` : corresponding wrappers (partially checked only in `delegateAmount`)
- **Mechanism:** Parallel arrays (`_amounts`, `_consensusAddrs`, src/dst) are not required to have equal lengths before looping. Mismatched lengths cause out-of-bounds reverts or, depending on calldata, mis-paired delegate/undelegate operations.
- **Impact:** Operator mistake can delegate/undelegate wrong amounts to wrong validators. Mostly operational, but a real logic footgun on a value-moving path.

---

## Stake on untracked validators is omitted from `totalAssets()`
- **Location:** `LiquidRon.sol` : `totalAssets`, `getTotalStaked`; `ValidatorTracker.sol` : `_tryPushValidator`
- **Mechanism:** `getTotalStaked()` only sums validators present in the internal `validators` list. A validator is added only when operator functions call `_tryPushValidator`. If stake exists on a consensus address never pushed (misconfiguration, migration, manual staking interaction), that stake is invisible to `totalAssets()`.
- **Impact:** NAV is understated; new depositors mint too many shares (dilution attack surface against existing LRON holders). Existing holders’ claims are backed by more RON than accounting reflects—later depositors extract value.

---

## `onlyOperator` modifier logic is inverted (broken operator ACL)
- **Location:** `LiquidRon.sol` : `onlyOperator`
- **Mechanism:**  
  ```solidity
  if (msg.sender != owner() || operator[msg.sender]) revert ErrInvalidOperator();
  ```
  This allows only `msg.sender == owner()` **and** `operator[owner] == false`. Any address marked `operator[true]` is blocked; non-owner operators can never pass.
- **Impact:** Not a direct external attacker privilege escalation (it is overly restrictive), but it breaks the intended separation of duties. If operators are expected to run harvest/delegation without the owner key, that security model fails operationally and concentrates risk on the owner key.

---

## `fetchOperatorFee` bypasses pause
- **Location:** `LiquidRon.sol` : `fetchOperatorFee`
- **Mechanism:** Fee withdrawal has no `whenNotPaused` while user exits are paused.
- **Impact:** During emergency pause, fee recipient can still extract accrued `operatorFeeAmount` while users cannot `withdraw`/`redeem`/finalize queued exits. Asymmetric pause behavior can remove liquidity precisely when users are locked.

---

### Items reviewed but not reported as standalone vulnerabilities
- **Escrow reentrancy / approval:** `Escrow.deposit` is vault-only; infinite approve to deployer vault is consistent with pull-based ERC4626 deposit.
- **Open `receive()` on `LiquidProxy`:** By itself is absorbed into harvest accounting; noted above only where it affects fund timing.
- **Rounding dust in epoch `redeem`:** Floor rounding favors the vault; not attacker-profitable.
- **Owner centralization (pause, fees, proxy deploy):** Trusted-admin assumptions unless combined with paths above (pause + queued withdrawals, fee fetch while paused).

---

### Highest-priority fixes (guidance only — Ask mode)
1. Add ERC4626 inflation mitigations (`_decimalsOffset`, minimum initial deposit, or dead shares) on the main deposit path.
2. Add withdrawal-request cancel or trustless finalization liveness guarantees.
3. Align undelegation with Ronin unbonding (track pending unbonding separately; do not credit vault until RON is received).
4. Fix `onlyOperator` to `msg.sender == owner() || operator[msg.sender]`.
5. Snapshot proxy balance before/after in `harvest`; fix `claimRewards` loop to pass one validator per iteration (or call once).

