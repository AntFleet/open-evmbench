# Audit: 2025-06-panoptic


An expert, uncensored, and complete smart-contract security audit report of the provided Solidity codebase is detailed below.

---

## 1. Zero-Fulfillment Epochs Permanently Lock Deposited Assets and Shares (Critical)
- **Location**: `src/HypoVault.sol` : `executeDeposit` and `executeWithdrawal`
- **Mechanism**: If the vault manager decides to fulfill 0 assets for a deposit epoch (e.g., `assetsToFulfill = 0` in `fulfillDeposits`), or 0 shares for a withdrawal epoch (e.g., `sharesToFulfill = 0` in `fulfillWithdrawals`), the state variables `assetsFulfilled` and `sharesFulfilled` for that epoch will be set to `0`. 
When users subsequently call `executeDeposit` or `executeWithdrawal` to process their requests for that epoch and roll over any unfulfilled portion, the contract performs division by `_depositEpochState.assetsFulfilled` and `_withdrawalEpochState.sharesFulfilled`, respectively:
  ```solidity
  // executeDeposit
  uint256 sharesReceived = Math.mulDiv(
      userAssetsDeposited,
      _depositEpochState.sharesReceived,
      _depositEpochState.assetsFulfilled // division by 0!
  );

  // executeWithdrawal
  uint256 assetsToWithdraw = Math.mulDiv(
      sharesToFulfill,
      _withdrawalEpochState.assetsReceived,
      _withdrawalEpochState.sharesFulfilled // division by 0!
  );
  ```
  Since `Math.mulDiv` reverts on a zero denominator, these functions will always revert. Furthermore, because both cancel and execute functions are bound to specific epoch states, historical epochs can no longer be processed, nor can they be cancelled because the manager can only cancel deposits/withdrawals for the *active, unfulfilled* epoch.
- **Impact**: All user deposits and withdrawals requested in an epoch where the manager fulfilled 0 assets/shares are permanently locked inside the contract. Affected users cannot retrieve their underlying tokens, mint their shares, or process their withdrawals, resulting in a permanent loss of funds.

---

## 2. Unminted "Ghost" Shares Lock 100% of Initial Depositor Assets (Critical)
- **Location**: `src/HypoVault.sol` : `constructor`
- **Mechanism**: In the constructor of `HypoVault.sol`, `totalSupply` is set to `1_000_000`:
  ```solidity
  constructor(...) {
      ...
      totalSupply = 1_000_000;
  }
  ```
  However, no address (such as `msg.sender`, the vault, or the manager) is minted these initial 1,000,000 shares (i.e. `balanceOf` is not updated for any address, so the sum of all individual balances remains `0`). These "ghost" shares permanently inflate the `totalSupply` denominator used to determine asset distribution when fulfilling withdrawals:
  ```solidity
  uint256 assetsReceived = Math.mulDiv(sharesToFulfill, totalAssets, _totalSupply);
  ```
- **Impact**: Any user who deposits and attempts to withdraw their shares will be heavily diluted. For instance, if the first user deposits and is minted 500,000 shares, the total supply becomes 1,500,000 shares. Even if the user requests to withdraw all 500,000 shares (which represents 100% of all actually owned shares in circulation), they will only receive `500,000 * totalAssets / 1,500,000 = 1/3` of the vault's assets. The remaining 2/3 of the assets will be permanently trapped inside the vault because the 1,000,000 ghost shares cannot be redeemed by anyone.

---

## 3. Accountant Wallet-Balance Absorption Flaw Allows NAV Manipulation and Permanent Vault Denial of Service (High/Critical)
- **Location**: `src/accountants/PanopticVaultAccountant.sol` : `computeNAV`
- **Mechanism**: When calculating the net asset value (NAV) of the vault, the contract iterates over the configured pools. If a pool's token matches one of the vault's tokens, the wallet balance of the vault is added directly to that pool's specific exposure:
  ```solidity
  if (!skipToken0)
      poolExposure0 += address(pools[i].token0) ==
          address(0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE)
          ? int256(address(_vault).balance)
          : int256(pools[i].token0.balanceOf(_vault));
  ```
  Later in the outer loop, each individual pool's exposure (including the absorbed wallet balance) is subjected to a `max(..., 0)` cap before being added to the cumulative `nav`:
  ```solidity
  nav += uint256(Math.max(poolExposure0 + poolExposure1, 0));
  ```
  If pool `i` has a net negative exposure (debt from options/borrowing) that exceeds the vault's liquid wallet balance of that token, the wallet balance is completely consumed and offset by the negative pool exposure, capping the combined value at `0`.
- **Impact**: This leads to two critical vulnerabilities:
  1. **NAV Manipulation**: The manager (or an external market event) can artificially decrease the reported NAV to `0` or near-0 by taking on some debt in a pool. While the NAV remains suppressed, malicious actors can deposit to get massive amounts of cheap shares. The manager can then close the debt position, suddenly inflating the NAV and allowing the attacker to withdraw for an immediate risk-free profit.
  2. **Denial of Service**: If a pool's debt
