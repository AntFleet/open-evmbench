# Audit: 2025-01-liquid-ron

# Smart Contract Security Audit — LiquidRon

## Broken `onlyOperator` access-control logic locks out all operators
- **Location:** `src/LiquidRon.sol` : `onlyOperator` modifier
- **Mechanism:** The modifier reads `if (msg.sender != owner() || operator[msg.sender]) revert ErrInvalidOperator();`. For the body to execute the caller must satisfy `msg.sender == owner()` **and** `operator[msg.sender] == false`. The intended condition is clearly `if (msg.sender != owner() && !operator[msg.sender])`. As written, the `||` and the un-negated `operator[msg.sender]` invert the logic: any address flagged as an operator is *rejected*, and any non-owner is rejected unconditionally.
- **Impact:** Every operator-gated function (`harvest`, `harvestAndDelegateRewards`, `delegateAmount`, `redelegateAmount`, `undelegateAmount`, `finaliseRonRewardsForEpoch`) can only ever be called by the owner, and the entire operator role is dead weight. Worse, if the owner is ever added via `updateOperator(owner, true)`, the condition `operator[owner]` becomes true and the owner is locked out too — every staking, delegation and, critically, `finaliseRonRewardsForEpoch` call reverts, freezing the withdrawal pipeline for all users until `updateOperator(owner,false)` is called.

## `totalAssets()` counts accrued operator fees as depositor assets
- **Location:** `src/LiquidRon.sol` : `totalAssets()` / `harvest` / `fetchOperatorFee`
- **Mechanism:** When `harvest` runs, the proxy wraps the full claimed reward into WRON and deposits it into the vault (`_depositRONTo(vault, claimedAmount)`), so the operator's fee share is physically sitting in the vault's WRON balance. The contract then accrues `operatorFeeAmount += (harvestedAmount * operatorFee) / BIPS`. However `totalAssets()` returns `super.totalAssets() + getTotalStaked() + getTotalRewards()`, where `super.totalAssets()` is the full WRON balance of the vault — including the un-paid `operatorFeeAmount`. The fee, which is a liability owed to `feeRecipient`, is never subtracted from `totalAssets()`. (Note the asymmetry: `getTotalRewards()` *does* subtract the fee on still-unclaimed rewards, but harvested rewards are over-counted.) The same is true for `harvestAndDelegateRewards`, where the fee is accrued against rewards that were re-staked, so the fee has no liquid backing at all yet `fetchOperatorFee` later pays it out of the vault's liquid WRON.
- **Impact:** The share price (`convertToAssets`) is inflated by `operatorFeeAmount` until `fetchOperatorFee` is called. A depositor can mint/redeem to capture the operator's fee: redeem just before the fee is withdrawn at the inflated price, leaving the remaining holders to absorb the drop when `fetchOperatorFee` removes that WRON. Conversely, late redeemers lose value the instant the fee is paid out. The protocol consistently mis-prices shares and leaks the operator-fee value to whoever exits first.

## ERC4626 first-depositor / inflation exposure with default zero decimals offset
- **Location:** `src/LiquidRon.sol` : `_convertToAssets` / `totalAssets` (no `_decimalsOffset` override)
- **Mechanism:** The vault never overrides `_decimalsOffset()`, so it defaults to `0` (only OZ’s single virtual share/asset protects the pool). `totalAssets()` is directly manipulable by anyone: WRON can be transferred straight to the vault address (counted by `getAssetsInVault()`), and native RON sent to the contract is wrapped and counted as well. An attacker who is the first depositor can mint a tiny number of shares and then donate a large amount to skew the `assets/shares` ratio.
- **Impact:** With a 0 offset the standard ERC4626 inflation attack is only weakly mitigated; an early attacker can round subsequent depositors’ minted shares down toward zero and capture a portion of their deposits. Setting a non-trivial `_decimalsOffset()` (e.g. returning a constant) is the standard mitigation.

## Operator-fee liability paid from liquidity it never backed (`harvestAndDelegateRewards`)
- **Location:** `src/LiquidRon.sol` : `harvestAndDelegateRewards`
- **Mechanism:** This path claims rewards and immediately re-delegates them via `delegateRewards`, so the harvested RON is added to *staked* balance, never entering the vault as liquid WRON. The function nonetheless executes `operatorFeeAmount += (harvestedAmount * operatorFee) / BIPS`. Later, `fetchOperatorFee` pays that accrued amount out of the vault's liquid WRON (`_withdrawRONTo`), which is composed of ordinary depositor funds — not the staked rewards the fee was levied against.
- **Impact:** The fee for re-staked rewards is effectively double-counted: the re-staked reward (fee portion included) keeps inflating depositor-facing `getTotalStaked()`/`totalAssets()`, while the same fee is simultaneously drained from depositor liquidity when `fetchOperatorFee` is called. This is a direct value leak from depositors to the fee recipient and can also force `fetchOperatorFee` to consume liquidity earmarked for pending withdrawals.

---

Note: `harvest()` in `LiquidProxy` calls `claimRewards(_consensusAddrs)` with the *entire* array on every loop iteration, which is redundant rather than exploitable, and the various array-length mismatches (`delegateAmount`, `redelegateAmount`) only cause reverts — I’ve excluded these as they are not security-relevant. The reentrancy surface in `withdraw`/`redeem`/`redeem(epoch)` is safe because shares are burned / `request.fulfilled` is set before the native-RON `call`.

