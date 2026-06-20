# Audit: 2024-05-munchables

## Unlock Time Bypass via `setLockDuration` Flaw
- Location: `src/managers/LockManager.sol` : `setLockDuration`
- Mechanism: In `setLockDuration`, the duration is intended to prevent users from reducing the lock time of existing stakes. However, the exact timing check is flawed: it verifies that `uint32(block.timestamp) + uint32(_duration) < lockedTokens[...].unlockTime`. If this validates, the new unlock time is calculated as `lastLockTime + uint32(_duration)`. Since `lastLockTime` is a timestamp from the past, a user can provide a smaller `_duration` equal to the *remaining* amount of time until unlock. This fulfills the `if` check, passing validation, but actively recalculates `unlockTime` to an endpoint that resides in the past (since `lastLockTime` was some time ago). 
- Impact: An attacker can fully bypass the lock duration and early-withdraw their locked ETH or ERC20 tokens before the expected `unlockTime` has elapsed.

## `lockOnBehalf` and `lock` Missing ETH Refund when Excess is Provide
- Location: `src/managers/LockManager.sol` : `_lock`
- Mechanism: A user can lock native ETH by calling the `lock` function with `_tokenContract` set to `address(0)`. In this workflow, if `msg.value != _quantity`, the transaction rightly reverts with `ETHValueIncorrectError`. However, if they target a given lock recipient through `lockOnBehalf` using WETH, or another ERC20 (where `_tokenContract != address(0)`), yet mistakenly send ETH in `msg.value` across the fallback, the system verifies `if (msg.value != 0) revert InvalidMessageValueError();`. However, the contract lacks any native ability to skim stranded/over-paid ETH out of itself securely, relying on generic fallback refusal. If forced somehow, unexpected behaviors may arise. (Though `msg.value` checks seem generally well-secured).

## Potential Griefing in Spray Proposal Execution
- Location: `src/managers/AccountManager.sol` : `execSprayProposal`
- Mechanism: Social roles can propose distributions ("squirts") of schnibbles to multiple addresses. However, when executing a proposal (`execSprayProposal`), it iterates an unbound array sequentially and operates state transitions. Since there's no cap or explicit limitation on `sprayProposals[_proposer].squirts.length` directly within execution matching Gas bounds explicitly (other than `MAX_SCHNIBBLE_SPRAY` = 100 on creation), massive squirt counts could theoretically hit block gas limits during execution. Worse, if one squirt address possesses adverse hooks (less likely here as the recipients are merely struct variables being incremented, not function calls).
- Impact: A malicious or compromised social proposer can configure an excessively large or duplicated array of recipients that costs exactly the block gas limit to execute, causing an administrative `execSprayProposal` to OOG (Out Of Gas) and denying schnibble claims.
