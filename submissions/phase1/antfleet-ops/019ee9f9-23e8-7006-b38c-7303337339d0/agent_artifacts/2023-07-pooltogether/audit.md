# Audit: 2023-07-pooltogether

# Security Audit: PoolTogether V5 Vault

Audit scope: `Vault.sol`, `VaultFactory.sol`, `IVaultHooks.sol` as provided. Dependencies (`TwabController`, `PrizePool`, `LiquidationPair`, `YieldVault`) are assumed non-malicious unless noted.

---

## Unrestricted `mintYieldFee` recipient enables fee theft

- **Location:** `Vault.sol` : `mintYieldFee`
- **Mechanism:** `mintYieldFee` decrements `_yieldFeeTotalSupply` and mints vault shares to `_recipient`, but never checks that `_recipient == _yieldFeeRecipient` (or any allowlist). The accrued fee balance is a permissionless mint right; only the decrement cap is enforced.
- **Impact:** Any address can call `mintYieldFee(_yieldFeeTotalSupply, attacker)` and mint all accrued yield-fee shares to themselves, stealing the entire yield-fee reserve from the configured recipient.

```solidity
function mintYieldFee(uint256 _shares, address _recipient) external {
  _requireVaultCollateralized();
  if (_shares > _yieldFeeTotalSupply) revert YieldFeeGTAvailable(_shares, _yieldFeeTotalSupply);

  _yieldFeeTotalSupply -= _shares;
  _mint(_recipient, _shares);  // no recipient validation
  ...
}
```

---

## Zero-cost deposit absorbs idle vault balance (yield theft)

- **Location:** `Vault.sol` : `_deposit` (via `deposit`, `mint`, `sponsor`, and permit variants)
- **Mechanism:** If the vault already holds underlying tokens (`_vaultAssets >= _assets`), `_deposit` skips `transferFrom` and still calls `_yieldVault.deposit(_assets, ...)` and mints full shares to `_receiver`. Idle balance is treated as if the caller paid it. Idle tokens count toward `_totalAssets()` and `availableYieldBalance()` (i.e. they are economically yield/reserves), but anyone can capture them by depositing.
- **Impact:** An attacker who observes or causes idle underlying in the vault (direct donation, dust left when `liquidate` does not sweep idle because `_amountOut < _vaultAssets`, etc.) can call `deposit(idleBalance, attacker)` paying nothing, receive depositor-priced shares, and steal yield that should be captured via liquidation or fee minting. They can also frontrun liquidation by depositing first. Existing depositors are diluted because yield backs new par-priced shares.

```solidity
if (_assets > _vaultAssets) {
  // only transfer the difference
  SafeERC20.safeTransferFrom(...);
}
// if _vaultAssets >= _assets: no transfer at all
_yieldVault.deposit(_assets, address(this));
_mint(_receiver, _shares);
```

---

## Unbounded claim fees allow compromised claimer to steal prizes

- **Location:** `Vault.sol` : `claimPrizes` / `_claimPrize`
- **Mechanism:** Only `msg.sender == _claimer` is enforced. `_feePerClaim` and `_feeRecipient` are fully caller-controlled with no cap and no tie to a governance-approved fee schedule. Each `_prizePool.claimPrize(..., _fee, _feeRecipient)` passes those values through.
- **Impact:** A malicious or compromised claimer can set `_feePerClaim` to `type(uint96).max` and `_feeRecipient` to themselves, draining winner payouts on every claim. This is a privileged-role abuse path with no on-chain guardrails.

---

## Silent `uint96` truncation in share mint/burn/transfer

- **Location:** `Vault.sol` : `_mint`, `_burn`, `_transfer`
- **Mechanism:** All TwabController balance updates cast `uint256` shares to `uint96` without a bounds check. `maxDeposit` / `maxMint` cap per-operation amounts at `type(uint96).max`, but `liquidate` mints `_amountOut` shares with no `uint96` ceiling, and cumulative operations are not otherwise prevented from reaching ranges where truncation matters.
- **Impact:** If `_shares > type(uint96).max`, the cast silently truncates. In `liquidate`, the liquidation pair is told `_amountOut` shares were minted while Twab may record far fewer, breaking accounting and enabling value extraction from the liquidator/protocol side. In the extreme, truncation can cause incorrect balances and broken TWAB/prize eligibility.

```solidity
_twabController.mint(_receiver, uint96(_shares));  // truncates, does not revert
```

---

## Prize-claim hooks can grief batch claims

- **Location:** `Vault.sol` : `setHooks`, `_claimPrize`, `claimPrizes`
- **Mechanism:** Any winner can set arbitrary hook implementations. `claimPrizes` loops over all winners in one transaction and calls `beforeClaimPrize` / `afterClaimPrize` on each winner’s hook with no try/catch. A hook that reverts (or consumes all gas) aborts the entire batch.
- **Impact:** A winner (or attacker who wins once) can block batch prize claims for all other winners in the same transaction. A malicious claimer can also be griefed when processing batches. Self-grief for a single winner is possible; batch denial is the main external impact.

---

## Withdrawals remain open while deposits are blocked during undercollateralization

- **Location:** `Vault.sol` : `maxDeposit` / `maxMint` vs inherited `maxWithdraw` / `maxRedeem` and `_withdraw`
- **Mechanism:** `maxDeposit` and `maxMint` return `0` when `!_isVaultCollateralized()`, but `maxWithdraw` / `maxRedeem` are not overridden and remain usable. After a yield-vault loss, `_currentExchangeRate()` drops below `_assetUnit`, deposits are frozen, but withdrawals still execute at the reduced rate.
- **Impact:** On insolvency, early withdrawers exit at the current impaired exchange rate while late withdrawers may be left with little or no backing (bank-run dynamics). This may be intentional, but it is a material economic risk for depositors and should be treated as a known protocol behavior rather than a safety guarantee.

---

## Permissionless `VaultFactory.deployVault` enables malicious vault deployments

- **Location:** `VaultFactory.sol` : `deployVault`
- **Mechanism:** Anyone can deploy a vault through the factory with arbitrary `_yieldVault`, `_prizePool`, `_owner`, and other parameters. The factory marks any deployment as `deployedVaults[vault] = true`.
- **Impact:** If integrators, frontends, or governance treat `deployedVaults` as a trust signal without validating constructor parameters, users can be directed into vaults wired to malicious yield vaults that steal deposits on `_yieldVault.deposit`. This is a deployment/trust-boundary issue, not a flaw in `Vault` logic itself, but it is exploitable in practice when combined with weak off-chain verification.

---

## Notes on reviewed areas (not reported as vulnerabilities)

The following were reviewed and are **not** reported as standalone findings given standard trust assumptions (non-malicious `YieldVault`, `PrizePool`, `LiquidationPair`, owner):

- **ERC777 reentrancy ordering** in `_deposit` / `_withdraw` — mitigated by intentional ordering; residual risk depends on a malicious token/yield vault.
- **Exchange-rate capping** in `_currentExchangeRate` — appears designed to exclude yield from depositor principal; mitigates classic ERC4626 inflation attacks on share price.
- **`liquidate` share-vs-asset comparison** (`_amountOut >= _vaultAssets`) — unit mismatch can leave idle dust or sweep idle early; operational/accounting quirk, not a direct theft path on its own.
- **`VaultFactory` / unset `_liquidationPair` at deploy** — operational/configuration risk until `setLiquidationPair` is called.

---

### Severity summary

| Severity | Finding |
|----------|---------|
| **Critical** | Unrestricted `mintYieldFee` recipient |
| **High** | Zero-cost deposit absorbs idle yield |
| **Medium** | Unbounded claim fees via claimer |
| **Medium** | `uint96` truncation |
| **Low** | Hook-based batch claim griefing |
| **Low / Design** | Withdrawals open when underwater |
| **Low / Trust** | Permissionless factory deployments |

The two findings that warrant immediate fix are **`mintYieldFee` recipient validation** (mint only to `_yieldFeeRecipient`, or remove the `_recipient` parameter) and **idle-balance handling in `_deposit`** (do not let callers mint shares against unowned idle balance without explicit accounting, e.g. sweep idle to yield vault first or require full `transferFrom` for user-initiated deposits).

