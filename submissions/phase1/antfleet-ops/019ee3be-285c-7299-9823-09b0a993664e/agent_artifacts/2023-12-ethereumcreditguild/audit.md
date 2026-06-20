# Audit: 2023-12-ethereumcreditguild

## Reentrancy via arbitrary external calls
- Location: src/core/CoreRef.sol : emergencyAction
- Mechanism: The function iterates over an arbitrary array of Call structs and performs `target.call{value: value}(callData)` (with no reentrancy guard, no checks on target, and no state updates between iterations) while holding the GOVERNOR role check only at entry.
- Impact: A GOVERNOR-controlled caller can supply a call that re-enters emergencyAction (or any CoreRef/Core function) to execute the remaining calls multiple times, drain ETH, or mutate Core roles/state before the original call completes.

## Gauge weight can be incremented for a term that has an unapplied loss
- Location: src/tokens/GuildToken.sol : _incrementGaugeWeight
- Mechanism: When `getUserGaugeWeight[user][gauge] == 0`, the function unconditionally sets `lastGaugeLossApplied[gauge][user] = block.timestamp` and proceeds to add weight, without verifying that `lastGaugeLoss[gauge]` has already been applied or that the gauge is live.
- Impact: An attacker who still holds GUILD can re-vote for (and therefore restore debt ceiling to) a term that suffered a loss, bypassing the intended freezing of the user's tokens until the loss is realized.

## PSM redemptions can be permanently bricked by repeated offboardings
- Location: src/governance/LendingTermOffboarding.sol : offboard / cleanup
- Mechanism: `nOffboardingsInProgress` is incremented in `offboard` and decremented in `cleanup`; the PSM is paused only on the transition 0→1 and unpaused only on 1→0. Nothing prevents a new `proposeOffboard`/`supportOffboard`/`offboard` cycle from being started while a previous cleanup is still pending.
- Impact: An attacker with sufficient GUILD weight can keep at least one offboarding in progress indefinitely, leaving PSM redemptions permanently disabled even after all loans are closed.

## Credit multiplier update uses stale totalSupply after surplus burn
- Location: src/governance/ProfitManager.sol : notifyPnL (loss path)
- Mechanism: When `loss > _surplusBuffer`, the code burns `_surplusBuffer` (which reduces `CreditToken.totalSupply()`) and then immediately reads `creditTotalSupply` to compute the new multiplier; the read occurs after the burn but the loss amount subtracted from the multiplier is the original `loss` value.
- Impact: The resulting `creditMultiplier` is too low, causing all existing CREDIT debt (including loans opened after the loss) to be overstated and allowing the attacker to extract more collateral than the economic loss warranted.

## Any user can call `bid` on an auction that already concluded
- Location: src/loan/AuctionHouse.sol : bid
- Mechanism: `getBidDetail` only checks `auctions[loanId].endTime == 0`; once `bid` (or `forgive`) has set `endTime`, a subsequent call still passes the check in `getBidDetail` because the early return for `endTime != 0` occurs after the `creditAsked` computation, but the function continues to call `LendingTerm.onBid` with stale auction data.
- Impact: A malicious bidder can force `onBid` to be invoked again, potentially transferring the same collateral multiple times or re-executing the PnL accounting with inconsistent values.

## `createVeto` accepts a timelockId that has already been executed or cancelled
- Location: src/governance/GuildVetoGovernor.sol : createVeto
- Mechanism: The only check is `timelockExecutionTime > 1`; a value of 1 (executed) or 0 (cancelled) is rejected, but nothing prevents a proposal from being created for an ID whose timestamp is still >1 at the moment of the call even though another actor is about to execute/cancel it in the same block.
- Impact: An attacker can create a veto proposal that immediately becomes Succeeded (or Canceled) in `state()`, wasting governance gas and allowing griefing of the timelock queue.
