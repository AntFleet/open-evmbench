# Audit: 2025-01-liquid-ron

## Accrued operator fees are counted as user-owned assets
- Location: `src/LiquidRon.sol` : `totalAssets`
- Mechanism: `harvest()` and `harvestAndDelegateRewards()` add the operator’s cut into `operatorFeeAmount`, but `totalAssets()` still returns the full WRON balance plus staked assets plus pending rewards without subtracting that already-reserved fee. As a result, ERC4626 share pricing treats assets owed to `feeRecipient` as if they still back LRON holders. New deposits made while `operatorFeeAmount > 0` mint too few shares, because the price per share is overstated until `fetchOperatorFee()` removes the fee from the vault.
- Impact: Existing holders and/or the fee recipient can make later depositors subsidize accrued fees. A victim depositing before `fetchOperatorFee()` receives fewer shares than they should, and loses value as soon as the fee is withdrawn.

## Anyone can hide claimable rewards from accounting by pruning validators
- Location: `src/LiquidRon.sol` : `pruneValidatorList`
- Mechanism: `pruneValidatorList()` decides whether a validator can be removed by checking rewards and stake across proxies, but it calls `IRoninValidator.getReward(vali, proxies[j])` with the arguments reversed. The interface expects `(user, validator)`, so this reads rewards for the validator address as if it were the staking user, which is effectively zero. After a proxy has undelegated all principal from a validator but still has unclaimed rewards there, any caller can make `canPrune` evaluate true and remove that validator from `validators`. `getTotalRewards()` then stops counting those rewards, even though operators can still later harvest them by passing the validator address directly.
- Impact: Any user can force `totalAssets()` to understate the vault’s real assets, then deposit at an artificially cheap share price or let pending withdrawers finalize at an undervalued price. When the hidden rewards are later harvested, the attacker captures value that belonged to existing holders.

## Deposits can bypass the emergency pause
- Location: `src/LiquidRon.sol` : `receive`
- Mechanism: The explicit deposit entry points use `whenNotPaused`, but the fallback native-RON path does not. Sending RON directly to the vault triggers `receive()`, which wraps the funds, forwards them through `Escrow`, and mints shares exactly like `deposit()`, even while the contract is paused.
- Impact: During an incident, attackers can keep entering the vault and minting shares despite the owner pausing the system. That defeats the pause as a containment control and allows continued exploitation of any pricing/accounting issue the pause was meant to stop.

## New depositors can capture rewards without actually staking through the reward period
- Location: `src/LiquidRon.sol` : `deposit`, `totalAssets`; `src/LiquidRon.sol` : `delegateAmount`
- Mechanism: Shares are minted immediately on deposit, but the deposited RON is not actually staked until a later operator call to `delegateAmount()`. Meanwhile share pricing only reflects whatever `IRoninValidator.getRewards()` exposes at that moment. Under Ronin’s delayed reward-period accounting, a user can deposit shortly before a reward rollover, receive shares before their capital has spent time staked, then exit after the rollover once those rewards become reflected in `totalAssets()`.
- Impact: A timed depositor can repeatedly skim yield that should belong to long-term stakers, earning rewards for periods in which their capital was never actually delegated or exposed to staking risk.

## The operator role is broken, turning critical flows into owner-only actions
- Location: `src/LiquidRon.sol` : `onlyOperator`
- Mechanism: The modifier uses `if (msg.sender != owner() || operator[msg.sender]) revert`, which is the inverse of the intended check. Any non-owner always reverts, and any address marked as an operator also reverts. In practice, `harvest`, `delegateAmount`, `redelegateAmount`, `undelegateAmount`, and `finaliseRonRewardsForEpoch` are callable only by the owner.
- Impact: Designated operators cannot service withdrawals or manage staking at all. This creates a single-key operational choke point; if the owner is unavailable or compromised, critical vault actions can be halted and user withdrawals can be blocked.

