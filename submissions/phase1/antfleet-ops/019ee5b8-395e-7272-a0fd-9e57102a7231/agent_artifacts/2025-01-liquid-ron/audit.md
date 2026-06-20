# Audit: 2025-01-liquid-ron

## Accrued operator fee is counted as user TVL
- Location: `src/LiquidRon.sol` : `totalAssets`, `harvest`, `harvestAndDelegateRewards`, `fetchOperatorFee`
- Mechanism: `harvest()` and `harvestAndDelegateRewards()` add the performance fee to `operatorFeeAmount`, but `totalAssets()` returns `super.totalAssets() + getTotalStaked() + getTotalRewards()` without subtracting that accrued fee liability. Once rewards are harvested, the gross rewards are counted in vault NAV while the fee remains claimable by `feeRecipient`. When `fetchOperatorFee()` later withdraws the fee, assets leave the vault without burning shares.
- Impact: Share price is inflated whenever `operatorFeeAmount > 0`. Existing holders can redeem before fee withdrawal and take a pro-rata share of fees owed to the operator; depositors entering during that window receive too few shares and lose value when the fee is fetched.

## Depositors can capture a reward-period update without having staked through the period
- Location: `src/LiquidRon.sol` : `deposit`, `receive`, `totalAssets`; `src/LiquidProxy.sol` : `harvest`
- Mechanism: Share minting prices deposits using current `totalAssets()`, including currently visible Ronin staking rewards via `getTotalRewards()`. The vault has no deposit lock, epoch-aware deposit fee, or reward-period guard. On Ronin, rewards become visible/claimable at period boundaries; an attacker can deposit just before the staking reward state updates, when the upcoming rewards are not yet reflected in `totalAssets()`, then withdraw after the update when those rewards are reflected.
- Impact: The attacker captures a pro-rata share of rewards earned by earlier stakers while contributing no stake during the reward period, diluting long-term depositors’ yield.

## Operator role access control is inverted
- Location: `src/LiquidRon.sol` : `onlyOperator`
- Mechanism: The modifier uses `if (msg.sender != owner() || operator[msg.sender]) revert ErrInvalidOperator();`. This only allows the owner when `operator[owner] == false`; every non-owner operator always reverts because `msg.sender != owner()` is true, and marking the owner as an operator bricks the owner too.
- Impact: Designated operators cannot call `harvest`, `delegateAmount`, `redelegateAmount`, `undelegateAmount`, or `finaliseRonRewardsForEpoch`. If the system depends on operators for staking management or withdrawal finalisation, those flows can be unavailable, locking users into delayed withdrawals until the owner directly performs the work, or permanently if the owner is accidentally marked as an operator.

