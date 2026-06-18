# Audit: 2023-07-pooltogether

Both reports are inline and the merge is mechanical — I'll do it directly rather than spawn agents. Mapping the findings:

- **A1** (Stolen yield fees in `mintYieldFee`) and **B1** (Unrestricted Yield Fee Minting) describe the same root cause and code path → one consensus finding.
- **A2, A3, A4, A5** appear only in Report A → single-reviewer.
- Report B has no findings beyond the shared one.

Here is the merged report.

---

# Merged Security Audit Report

## Consensus findings

## Unrestricted / caller-controlled yield-fee minting in `mintYieldFee`
*(consensus)*
- Location: `vault/src/Vault.sol` : `mintYieldFee(uint256 _shares, address _recipient)` (around lines 365–373)
- Mechanism: `mintYieldFee` is `external` with **no caller restriction** and mints to a **caller-supplied** `_recipient`. The accrued protocol yield fee is tracked in `_yieldFeeTotalSupply` (incremented on every `liquidate` call) and is intended to be mintable only to the configured `_yieldFeeRecipient`. The function checks `_shares > _yieldFeeTotalSupply`, decrements `_yieldFeeTotalSupply -= _shares`, then `_mint(_recipient, _shares)` to the attacker-controlled address — it never requires `msg.sender` to be the owner, the configured `_yieldFeeRecipient`, or any authorized fee manager. The stored `_yieldFeeRecipient` (and its setter `setYieldFeeRecipient`) is never consulted here and is effectively dead state. Preconditions: `_yieldFeeTotalSupply > 0` and the vault is collateralized (`_requireVaultCollateralized`).
  ```solidity
  function mintYieldFee(uint256 _shares, address _recipient) external {
    _requireVaultCollateralized();
    if (_shares > _yieldFeeTotalSupply) revert YieldFeeGTAvailable(_shares, _yieldFeeTotalSupply);
    _yieldFeeTotalSupply -= _shares;
    _mint(_recipient, _shares);   // _recipient is attacker-controlled
    ...
  }
  ```
  Fix: drop the `_recipient` parameter and mint to `_yieldFeeRecipient`, or require `msg.sender == _yieldFeeRecipient`.
- Impact: Once yield fees have accrued through liquidation, any external account can call `mintYieldFee(_yieldFeeTotalSupply, attackerAddress)` and receive all accrued yield-fee shares for free. These are real, fully-backed vault shares immediately redeemable for the underlying asset. Every fee the protocol accrues from liquidations can be front-run and drained by an arbitrary attacker; the legitimate `_yieldFeeRecipient` receives nothing. Direct, repeatable theft of protocol revenue (high severity).

## Additional findings (single-reviewer)

## Silent `uint96` truncation with event/contribution desync on mint
*(Reviewer A only)*
- Location: `vault/src/Vault.sol` : `_mint` / `_burn` / `_transfer` (the `_twabController.mint/burn/transfer(..., uint96(_shares))` casts), reached from `liquidate`
- Mechanism: Balances are stored as `uint96` in the TwabController, and the vault casts `uint96(_shares)` before writing, while the corresponding `Transfer` event (and, in `liquidate`, the `_prizePool.contributePrizeTokens(_amountIn)` accounting and the `_increaseYieldFeeBalance` computation) uses the full `uint256` value. In the deposit/mint/withdraw paths shares are provably bounded to `type(uint96).max` by `maxDeposit`/`maxMint`/`maxRedeem`, so they are safe. But `liquidate` mints `_amountOut` bounded only by `_liquidatableBalanceOf` (available yield), which is **not** clamped to `uint96.max`. If accrued yield exceeds `2^96`, `uint96(_amountOut)` silently truncates the minted balance while the emitted `Transfer`/`Deposit`-style accounting and prize-pool contribution reflect the full amount.
- Impact: When liquidatable yield exceeds `uint96.max`, the on-chain share balance written for the liquidator is a tiny truncated remainder, yet the event log and the prize-pool contribution record the full value — an event-vs-storage desync that corrupts off-chain accounting and causes the liquidator to overpay prize tokens for far fewer shares than recorded. Requires a very large yield accrual, so lower severity, but it is an unbounded-input truncation in a value-bearing path that should be range-checked.

## Idle / donated asset balance credited to the next depositor
*(Reviewer A only)*
- Location: `vault/src/Vault.sol` : `_deposit` (the `_vaultAssets`/`_assetsDeposit` branch)
- Mechanism: `_deposit` reads the vault's raw token balance and only pulls `_assets - _vaultAssets` from the caller (and nothing at all when `_assets <= _vaultAssets`), but always mints shares for the full `_assets` and deposits the full `_assets` into the yield vault:
  ```solidity
  uint256 _vaultAssets = _asset.balanceOf(address(this));
  if (_assets > _vaultAssets) { ... safeTransferFrom(...,_assets - _vaultAssets); }
  _yieldVault.deposit(_assets, address(this));
  _mint(_receiver, _shares);
  ```
  Any underlying tokens sitting idle in the vault are simultaneously counted as available yield (because `_totalAssets()` includes `super.totalAssets()` = the vault's raw balance, which feeds `availableYieldBalance`). So idle balance is "double-purposed": it counts as liquidatable yield destined for the prize pool, yet here it is silently consumed to back a depositor's freshly minted shares.
- Impact: An attacker can front-run any donation/leftover idle balance with a `deposit` whose `_assets` is ≤ the idle balance, minting vault shares while paying little or nothing, capturing value that was otherwise accounted as yield for the prize pool / other depositors. No flash loan required; only an idle balance must exist. Severity depends on how often idle asset balances arise, but the accounting path is genuinely exploitable when they do.

## Unbounded attacker-controlled hooks invoked inside the claim loop
*(Reviewer A only)*
- Location: `vault/src/Vault.sol` : `_claimPrize` (calls `hooks.implementation.beforeClaimPrize` / `afterClaimPrize`), reached from `claimPrizes`
- Mechanism: Any address can register arbitrary hook contracts for itself via `setHooks` (no restriction). During `claimPrizes`, the claimer iterates over `_winners` and for each winner calls that winner's `beforeClaimPrize`/`afterClaimPrize` with no gas cap, no try/catch, and no reentrancy guard. `beforeClaimPrize` even returns the `recipient` address used in `_prizePool.claimPrize`. A malicious hook can revert, consume unbounded gas, or reenter vault/prize-pool functions mid-loop.
- Impact: A single malicious winner included in a batch can force the entire `claimPrizes` transaction to revert or run out of gas, a denial-of-service against the claimer's batched claims (the claimer must detect and exclude the griefer). The hook also opens a reentrancy surface into a non-guarded state-changing flow. Self-directed prize redirection is by design, but the unbounded external call in a shared loop is a real availability risk.

## `setYieldFeePercentage` admits 100%, disabling liquidation
*(Reviewer A only)*
- Location: `vault/src/Vault.sol` : `_setYieldFeePercentage` (called from `setYieldFeePercentage`)
- Mechanism: The bound check is `if (yieldFeePercentage_ > FEE_PRECISION)`, so `_yieldFeePercentage == FEE_PRECISION` (100%) is accepted. At 100%, `_liquidatableBalanceOf` returns `availableYield - availableYield*100% = 0`, so all liquidations revert (`LiquidationAmountOutGTYield`), and the fee term in `liquidate`, `(_amountOut * FEE_PRECISION) / (FEE_PRECISION - _yieldFeePercentage)`, divides by zero. All yield is diverted to the fee bucket and none can ever reach the prize pool.
- Impact: An owner (or a fat-fingered config) can brick the entire liquidation/prize flow by setting the fee to exactly 100%; the check should be `>=`. Owner-only and reversible by lowering the fee, so this is a configuration foot-gun rather than an external exploit, but it is a setter that admits an invalid boundary value that breaks downstream logic.

