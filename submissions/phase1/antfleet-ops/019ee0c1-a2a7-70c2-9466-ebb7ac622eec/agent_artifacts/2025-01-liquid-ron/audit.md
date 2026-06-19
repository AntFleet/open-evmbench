# Audit: 2025-01-liquid-ron

## Accrued operator fees are still counted as user assets
- Location: `src/LiquidRon.sol` : `totalAssets`, `harvest`, `harvestAndDelegateRewards`, `fetchOperatorFee`
- Mechanism: Harvested rewards are deposited or restaked in full, and `operatorFeeAmount` is incremented as a liability. However `totalAssets()` never subtracts `operatorFeeAmount`. After harvest, the vault reports fee-reserved assets as backing LRON shares until `fetchOperatorFee()` removes them.
- Impact: Share price is overstated. Users can redeem/withdraw after harvest but before fee collection and extract assets that should belong to the fee recipient, pushing the loss onto remaining holders. Conversely, users depositing during that window receive too few shares and subsidize previously accrued fees.

## Withdrawal claims underpay users and trap funds in escrow
- Location: `src/LiquidRon.sol` : `redeem(uint256)`, `_convertToAssets`
- Mechanism: Epoch withdrawals first move a fixed amount of WRON into `escrow`, then each user’s claim is calculated with `_convertToAssets(shares, assetSupply, shareSupply)`. That function reuses the ERC4626 virtual asset/share formula: `(_totalAssets + 1) / (_totalShares + 10 ** _decimalsOffset())`. For distributing a fixed escrowed pool, those virtual offsets are wrong; a user redeeming all locked shares receives `lockedShares * (assets + 1) / (lockedShares + 1)`, which is less than the escrowed assets whenever price per share is above 1.
- Impact: Withdrawal requesters can receive less RON than was finalized for their epoch. The unclaimed difference remains stuck in `Escrow` with no recovery path, causing permanent user loss and accounting drift.

## Operator access control is inverted
- Location: `src/LiquidRon.sol` : `onlyOperator`
- Mechanism: The modifier uses `if (msg.sender != owner() || operator[msg.sender]) revert ErrInvalidOperator();`. This allows only the owner when `operator[owner] == false`; every non-owner operator always reverts because `msg.sender != owner()` is true. The intended check should be owner-or-approved-operator, but the implemented logic denies approved operators.
- Impact: Designated operators cannot harvest, delegate, undelegate, redelegate, or finalize withdrawal epochs. If the owner is unavailable or operational control was delegated to operators, withdrawals and staking operations can be frozen.

