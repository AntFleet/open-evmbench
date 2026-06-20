# Audit: 2025-02-thorwallet

## Merge accounting is not capped to the TITN reserve
- Location: `contracts/MergeTgt.sol` : `onTokenTransfer`
- Mechanism: The contract credits `claimableTitnPerUser[from] += quoteTitn(amount)` without enforcing that aggregate claimable TITN stays within the deposited `TITN_ARB` reserve or that total exchanged TGT stays below `TGT_TO_EXCHANGE`. Once users send more than the assumed 579M TGT exchange amount, `totalTitnClaimable` can exceed the actual TITN balance.
- Impact: Early claimers can drain the TITN reserve, leaving later claimants unable to claim. If over-allocation remains until year end, `withdrawRemainingTitn` can also underflow on `remainingTitnAfter1Year - initialTotalClaimable`, permanently DoSing remaining withdrawals unless more TITN is added.

## Last-minute dust claim can capture the remaining TITN pool
- Location: `contracts/MergeTgt.sol` : `withdrawRemainingTitn`
- Mechanism: After 360 days, the remaining TITN balance is distributed pro-rata only across the then-current `totalTitnClaimable`, which excludes users who already claimed before the deadline. An attacker can wait until just before 360 days, send enough TGT to create a small positive claimable amount, then call `withdrawRemainingTitn` after the deadline. If other users have already claimed, the attacker’s tiny claimable balance can become most or all of `initialTotalClaimable`.
- Impact: The attacker can receive far more TITN than their quoted exchange amount and potentially drain the entire remaining TITN balance for a negligible late-stage TGT deposit.

## Deadline boundary accepts TGT for zero TITN
- Location: `contracts/MergeTgt.sol` : `onTokenTransfer`
- Mechanism: `onTokenTransfer` rejects only when `block.timestamp - launchTime > 360 days`, but `quoteTitn` returns zero when `timeSinceLaunch >= 360 days`. At exactly `launchTime + 360 days`, TGT transfers are accepted and credited with `titnOut == 0`.
- Impact: A user who merges at the exact deadline loses TGT without receiving any claimable TITN.

## Owner can withdraw escrowed user funds
- Location: `contracts/MergeTgt.sol` : `withdraw`
- Mechanism: `withdraw` allows the owner to transfer any ERC20 from the merge contract, including TITN already backing user claim balances. It does not preserve `totalTitnClaimable`, check available surplus, or restrict withdrawals to non-claim backing funds.
- Impact: A malicious or compromised owner can drain TITN owed to users, causing `claimTitn` and `withdrawRemainingTitn` to fail or pay less than promised.

## Bridged-token lock does not follow bridged tokens after transfer
- Location: `contracts/Titn.sol` : `_credit`, `_validateTransfer`
- Mechanism: Bridged status is tracked per address in `isBridgedTokenHolder`, not per token balance. `_credit` marks only the initial bridge recipient. If bridged tokens later move while transfers are unlocked, or through an allowed contract path, the recipient is not marked as a bridged holder. On non-Arbitrum chains, `_validateTransfer` then treats that recipient as unrestricted.
- Impact: Bridged tokens can be laundered into unmarked addresses and transferred despite the intended bridged-token transfer lock.

