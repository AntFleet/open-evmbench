# Audit: 2025-01-liquid-ron

I found three genuine issues.

## Accrued operator fees are counted as user assets
- Location: `src/LiquidRon.sol` : `harvest`, `harvestAndDelegateRewards`, `totalAssets`, `fetchOperatorFee`
- Mechanism: `harvest` and `harvestAndDelegateRewards` accrue `operatorFeeAmount`, but `totalAssets()` never subtracts that accrued fee liability once rewards have been harvested or delegated. Before harvest, `getTotalRewards()` subtracts the fee from pending rewards. After harvest, the gross reward is included through `super.totalAssets()` or `getTotalStaked()`, while the fee remains withdrawable separately via `fetchOperatorFee()`.
- Impact: The share price is inflated by unpaid operator fees. Users depositing during this window receive too few shares, and users redeeming before `fetchOperatorFee()` can withdraw value that should be reserved for fees. When the fee recipient later calls `fetchOperatorFee()`, assets are removed without burning shares, shifting the loss to whoever remains in the vault.

## Operator access control is inverted
- Location: `src/LiquidRon.sol` : `onlyOperator`
- Mechanism: The modifier uses `if (msg.sender != owner() || operator[msg.sender]) revert ErrInvalidOperator();`. This allows only the owner when `operator[owner] == false`. Any configured operator always fails because `msg.sender != owner()` is true, and the owner also fails if marked as an operator. The intended condition appears to be owner OR approved operator.
- Impact: Non-owner operators cannot call staking, harvesting, undelegation, or withdrawal-finalization functions. If the system relies on operators for liveness, withdrawals requiring `finaliseRonRewardsForEpoch()` and staking maintenance can be blocked until the owner acts.

## Queued withdrawals can be permanently stuck for some contract accounts
- Location: `src/LiquidRon.sol` : `requestWithdrawal`, `_checkUserCanReceiveRon`, `redeem(uint256)`
- Mechanism: `requestWithdrawal` checks whether `msg.sender` can receive RON using a zero-value call. A contract with a nonpayable fallback can accept a zero-value call but reject the later nonzero RON transfer in `redeem(uint256)`. The queued withdrawal has no alternate receiver parameter, and after finalization the shares are burned and the claim is bound to `msg.sender`.
- Impact: Contract accounts that pass the zero-value check but reject nonzero native RON can lock their finalized withdrawal assets in escrow with no recovery path through the vault.

