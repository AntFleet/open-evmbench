# Audit: 2023-07-pooltogether
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Accrued yield fees stealable via `mintYieldFee` (no access control, caller-controlled recipient)
*(consensus, 6 of 6 reports)*
- Location: `vault/src/Vault.sol` : `mintYieldFee(uint256 _shares, address _recipient)`
- Mechanism: The function is `external` with no `onlyOwner`/role check and mints to a fully caller-supplied `_recipient`. It only validates `_shares <= _yieldFeeTotalSupply`, then `_yieldFeeTotalSupply -= _shares; _mint(_recipient, _shares);`. The contract maintains a dedicated `_yieldFeeRecipient` storage variable (with an `onlyOwner` setter), so the mint is supposed to depend on that state — not on a parameter. The guard bounds only the amount, never who receives it.
- Impact: Any unprivileged account can call `mintYieldFee(yieldFeeTotalSupply(), attacker)` and mint the entire accrued yield-fee balance as real vault shares to itself, then redeem/withdraw for underlying. Direct, repeatable theft of all protocol yield fees. Precondition: vault collateralized (normal state) and `_yieldFeeTotalSupply > 0`.
- Reviewer disagreement: none — all six reports flag it.

## Silent `uint96` truncation in `_mint`/`_burn`/`_transfer` (event vs. storage desync)
*(consensus, 6 of 6 reports)*
- Location: `vault/src/Vault.sol` : `_mint`, `_burn`, `_transfer` (the "State Functions" block)
- Mechanism: Balances live in `TwabController` as `uint96`, but the ERC-20/4626 surface is `uint256`. Each override does an unchecked downcast — `_twabController.mint(_receiver, uint96(_shares))` etc. — while emitting the **full untruncated** `uint256` in the `Transfer` event. `deposit`/`mint` are bounded by `maxDeposit`/`maxMint` (`type(uint96).max`), but `liquidate` (`_amountOut`), `mintYieldFee` (`_shares`), and direct `transfer`/`transferFrom` reach these functions with **no `uint96` bound**. Values `> 2^96-1` wrap modulo 2^96 in storage. In `mintYieldFee` the full `_yieldFeeTotalSupply` is decremented while only a tiny wrapped value is minted; in `liquidate` the full `_amountOut` is recorded against accounting while a truncated balance is stored.
- Impact: Emitted events / prize/fee accounting / indexers diverge from real stored balances. Under high-yield conditions a liquidator pays prize tokens for the full `_amountOut` but receives only the truncated remainder; fee accounting is permanently corrupted. Several reports note the realistic precondition is an extreme yield balance (>~7.9e28 base units), so they rate it latent correctness/defense-in-depth, but the unchecked cast and missing per-path `uint96` guard are real.
- Reviewer disagreement: none on existence; reports differ only on severity (cheap exploit vs. latent defect).

## Idle/donated underlying assets credited to the next depositor for free
*(consensus, 4 of 6 reports)*
- Location: `vault/src/Vault.sol` : `_deposit` (the `if (_assets > _vaultAssets)` block), and `liquidate` idle-sweep
- Mechanism: `_deposit` reads the vault's raw underlying balance. When `_assets <= balanceOf(address(this))` the `if (_assets > _vaultAssets)` guard is false, so **no `safeTransferFrom` runs**, yet `_yieldVault.deposit(_assets, address(this))` and `_mint(_receiver, _shares)` still execute, funded from the idle balance. Idle assets (direct donations, accidental sends, stranded liquidation residue) are treated as depositor-supplied principal. `liquidate` only re-deposits idle assets when `_amountOut >= _vaultAssets` (a share-vs-asset comparison), so residue can remain.
- Impact: Whoever deposits first after idle assets accumulate mints fully-backed shares with reduced or zero payment, then redeems them to extract the idle balance — capturing donations, accidental sends, or stranded liquidation leftovers.
- Reviewer disagreement: opus-4-8 shot 2 examined the `_deposit` idle-asset arithmetic and judged it sound ("cannot underflow given `_yieldFeePercentage <= FEE_PRECISION`"); opus-4-8 shot 1 argued direct donations are "treated as yield" (neutralizing the classic inflation attack) rather than credited to a depositor. *(conflicting reviews: 2 of 6 reports addressed this code path and did not flag it as exploitable)*

## `setYieldFeePercentage` accepts 100% (`FEE_PRECISION`), bricking liquidation + latent divide-by-zero
*(consensus, 2 of 6 reports)*
- Location: `vault/src/Vault.sol` : `_setYieldFeePercentage` (validation), interacting with `liquidate` and `_liquidatableBalanceOf`
- Mechanism: The guard rejects only `yieldFeePercentage_ > FEE_PRECISION`, so exactly 100% (`== FEE_PRECISION`) is allowed. At 100%, `_liquidatableBalanceOf` returns `availableYield - availableYield*1e9/1e9 = 0`, so every `liquidate` reverts; separately, `liquidate`'s `(_amountOut * FEE_PRECISION) / (FEE_PRECISION - _yieldFeePercentage)` divides by zero. Bound should be exclusive (`>=`).
- Impact: An owner setting the fee to 100% permanently disables all liquidation, yield→prize-token conversion, and prize-pool funding until the value is lowered. Owner-gated, so a configuration footgun/brick rather than an external attack.
- Reviewer disagreement: opus-4-8 shot 2 defended the path — argued the divide-by-zero is unreachable because at 100% fee `_liquidatableBalanceOf` returns 0 and `liquidate` reverts earlier on the zero-liquidatable check. *(conflicting reviews: 1 of 6 reports defended this code path)*

## Minority findings

## User-controlled claim hooks can grief the entire batch claim
*(minority, 1 of 6 reports)*
- Location: `vault/src/Vault.sol` : `_claimPrize` (called in a loop from `claimPrizes`)
- Mechanism: For each winner, `_claimPrize` invokes the winner-configured `beforeClaimPrize`/`afterClaimPrize` hooks (set permissionlessly via `setHooks`) with no gas cap and no try/catch, inside the single-transaction `claimPrizes` loop over all winners.
- Impact: A malicious winner registers a hook that reverts or consumes unbounded gas; because the whole batch is one transaction, one such hook reverts it, denying claims to every other winner and wasting the claimer's gas. Cheaply repeatable. (Later contract versions added explicit gas limits for exactly this reason.)
- Reviewer disagreement: opus-4-8 shot 3 defended the path — `claimPrizes` is gated to the trusted `_claimer` and each winner controls only their own recipient, so this is "claimer-borne gas-griefing inherent to the hook design" with no fund-theft/reentrancy. *(conflicting reviews: 1 of 6 reports defended this code path)*

## `maxDeposit`/`maxMint` overstate the true cap at the boundary (total-supply overflow)
*(minority, 1 of 6 reports)*
- Location: `vault/src/Vault.sol` : `maxDeposit`, `maxMint`
- Mechanism: Both return `type(uint96).max` whenever the vault is collateralized, independent of existing supply. `TwabController` stores total supply as `uint96`, so minting `type(uint96).max` while supply is already non-zero overflows the controller's total-supply accumulator and reverts.
- Impact: ERC-4626 requires these views to return an amount that won't revert the corresponding `deposit`/`mint`. Near the cap (or any non-trivial existing supply) the reported max is unachievable; integrators sizing deposits off these views hit unexpected reverts. Availability/spec-conformance bug.
- Reviewer disagreement: opus-4-8 shot 2 treated `maxDeposit`/`maxMint = type(uint96).max` as a sound protective bound and relied on it to argue deposit-path truncation is unreachable. *(conflicting reviews: 1 of 6 reports relied on this cap as correct)*

## Liquidation fee avoided by splitting into small fills (fee rounds to zero)
*(minority, 1 of 6 reports)*
- Location: `vault/src/Vault.sol` : `liquidate`, `_availableYieldFeeBalance`
- Mechanism: `liquidatableBalanceOf` reserves fees against total available yield, but `liquidate` accrues fees per-fill with downward-rounded integer math: `(_amountOut * FEE_PRECISION) / (FEE_PRECISION - _yieldFeePercentage) - _amountOut`. For sufficiently small `_amountOut` the fee rounds to zero, and repeated tiny partial liquidations drain yield without growing `_yieldFeeTotalSupply`.
- Impact: Liquidators bypass protocol/yield-recipient fees and liquidate nearly all available yield as fee-free shares. Preconditions: non-zero yield fee percentage and a liquidation pair permitting small partial fills.
- Reviewer disagreement: opus-4-8 shots 1 & 2 asserted the liquidation fee math/rounding "favors the vault" and that `_liquidatableBalanceOf` "cannot underflow." *(conflicting reviews: 2 of 6 reports characterized this fee math as sound)*

## Liquidation fee rounding over-allocates yield and can undercollateralize the vault
*(minority, 1 of 6 reports)*
- Location: `vault/src/Vault.sol` : `_liquidatableBalanceOf`, `_availableYieldFeeBalance`, `liquidate`
- Mechanism: `_liquidatableBalanceOf` computes `availableYield - floor(availableYield * fee / precision)`, which can round the net liquidatable amount **up**; `liquidate` then grosses up `_amountOut` to compute fee shares. Example: `availableYield = 3`, 50% fee → `_liquidatableBalanceOf` allows `2` out, but `liquidate` accrues `2` fee shares, allocating `4` total shares against only `3` assets of yield.
- Impact: A boundary liquidation creates unbacked fee shares; combined with the public `mintYieldFee` an attacker mints them, and even with access fixed the fee recipient could mint shares that dilute depositors and push the vault undercollateralized. Preconditions: non-zero fee percentage and a non-exactly-divisible rounding case.
- Reviewer disagreement: opus-4-8 shots 1 & 2 asserted the `_liquidatableBalanceOf` fee math favors the vault / cannot underflow. *(conflicting reviews: 2 of 6 reports characterized this fee math as sound)*

## Anyone can force another account into sponsorship delegation
*(minority, 1 of 6 reports)*
- Location: `vault/src/Vault.sol` : `sponsor`, `sponsorWithPermit`, `_sponsor`
- Mechanism: `_sponsor` accepts an arbitrary `_receiver` and unconditionally calls `_twabController.sponsor(_receiver)` after depositing (when the receiver isn't already delegated to the sponsorship address). No authorization or consent check from `_receiver`.
- Impact: An attacker deposits dust (or zero, if the downstream vault permits zero deposits) for a victim and forces the victim's TWAB delegation to the sponsorship address, removing/redirecting prize eligibility until the victim notices and redelegates.
- Reviewer disagreement: none — no other report addressed this code path.

## Zero-withdrawable insolvency treated as fully collateralized
*(minority, 1 of 6 reports)*
- Location: `vault/src/Vault.sol` : `_currentExchangeRate`, `_isVaultCollateralized`, `deposit`, `mint`
- Mechanism: `_currentExchangeRate` returns `_assetUnit` (1:1) whenever `_totalSupplyAmount != 0` but `_yieldVault.maxWithdraw(address(this)) == 0`, because the real calculation only runs when both values are non-zero. An existing-supply vault with zero withdrawable assets therefore appears 1:1 collateralized instead of insolvent, leaving `maxDeposit`/`maxMint`/`deposit`/`mint` open.
- Impact: If the yield vault becomes fully illiquid or loses all withdrawable assets while shares still exist, new depositors enter at a false 1:1 rate; their assets recapitalize old shares, letting existing shareholders withdraw value from the new deposits. Preconditions: non-zero share supply and `yieldVault.maxWithdraw(address(this)) == 0`.
- Reviewer disagreement: opus-4-8 shot 2 explicitly defended this path — "`availableYieldBalance`/`_currentExchangeRate` correctly clamp to avoid minting against uncollateralized state." *(conflicting reviews: 1 of 6 reports defended this code path)*

---

*Reconciliation check: 10 distinct findings identified across the 6 input reports (by code path + root cause); 10 findings emitted (4 consensus, 6 minority). No findings dropped.*

