# Audit: 2024-01-init-capital-invitational

## Reentrancy via external reward/claim flows
- Location: contracts/wrapper/WLpMoeMasterChef.sol : wrap/unwrap/harvest + _claimFromMasterChef/_transferRewards (and updateRewards modifier)
- Mechanism: No ReentrancyGuard on the contract (unlike InitCore/MoneyMarketHook). wrap/unwrap/harvest call IMasterChef.deposit/withdraw/claim (and token.transfer) while __lpBalances/idAccRewardPerShares_e18 are updated only after the external call; reward tokens or a malicious/extra rewarder can re-enter via hooks or callbacks before balances and pidAccRewardPerShares_e18 are finalized.
- Impact: Attacker controlling a reward token or rewarder can re-enter to double-claim rewards, manipulate per-id accounting, or drain LP/reward balances belonging to the position.

## Missing access control on initialize
- Location: contracts/hook/MarginTradingHook.sol : initialize
- Mechanism: initialize (which sets the privileged swapHelper) is external and has no onlyGovernor/onlyOwner guard or _disableInitializers in the constructor (only BaseMappingIdHook constructor runs); any caller can invoke it after deployment.
- Impact: Attacker can overwrite swapHelper to a malicious contract that steals tokens or performs unauthorized swaps during coreCallback in openPos/increasePos/reducePos.

## Oracle price used without staleness bound on order fill
- Location: contracts/hook/MarginTradingHook.sol : fillOrder + _validateTriggerPrice
- Mechanism: _validateTriggerPrice reads markPrice_e36 directly from IInitOracle.getPrice_e36 (via base/quote) with no call to maxStaleTime checks that exist in Pyth/Api3 readers; the order's trigger/limit price test therefore uses potentially stale data.
- Impact: Attacker can wait for an oracle price to become stale/out-of-date and force-fill stop-loss/take-profit orders at incorrect prices, causing loss to the order owner.

## Debt snapshot uses stored vs. current amount inconsistently
- Location: contracts/core/PosManager.sol : updatePosDebtShares
- Mechanism: interest = debtAmtCurrent(...) - lastDebtAmt then lastDebtAmt is set to debtShareToAmtStored(newDebtShares); the two ILendingPool calls straddle an accrueInterest boundary inside the same external borrow/repay path.
- Impact: totalInterest accumulator (used by hooks/lens) can be inflated or under-reported, leading to incorrect reward/interest accounting visible to position viewers or liquidators.

## Flashloan distinct-pool check can be bypassed by duplicate pools
- Location: contracts/core/InitCore.sol : flash + _validateFlash
- Mechanism: _validateFlash calls AddressArrayLib.isSortedAndNotDuplicate which returns true for length-1 arrays; a caller can therefore supply a single-element _pools/_amts array (or carefully ordered duplicates) and still pass, avoiding the "distinct addresses to avoid paying less flash fees" intent.
- Impact: Attacker can obtain multiple flashloans of the same asset in one call while paying only a single fee, or grief the fee accounting inside the pool.

## Unchecked initialize on upgradeable contracts
- Location: contracts/lending_pool/LendingPool.sol, contracts/risk_manager/RiskManager.sol, contracts/oracle/* (multiple)
- Mechanism: Constructors call _disableInitializers but several non-proxy contracts (LendingPool, RiskManager, Api3OracleReader, etc.) expose public/external initialize without a subsequent guard; an attacker can call initialize after the first legitimate call if the proxy admin is ever changed or if a new implementation is deployed.
- Impact: Attacker can re-initialize critical parameters (irm, oracle sources, maxStaleTime, debt ceilings) and brick or take over the protocol.
