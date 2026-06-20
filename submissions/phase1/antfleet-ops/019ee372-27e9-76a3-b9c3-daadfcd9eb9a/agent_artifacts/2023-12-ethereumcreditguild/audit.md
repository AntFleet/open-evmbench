# Audit: 2023-12-ethereumcreditguild

## Uninitialized `userStake` leads to unjustified slashing of new stakers
- Location: `src/loan/SurplusGuildMinter.sol` : `getRewards`
- Mechanism: In `getRewards`, the code checks if `lastGaugeLoss > uint256(userStake.lastGaugeLoss)` to determine if a user should be `slashed`. However, this check is performed *before* `userStake` is actually loaded from storage (`userStake = _stakes[user][term];`). Because `userStake` is an uninitialized return variable at the time of the check, `userStake.lastGaugeLoss` will always evaluate to `0`. Consequently, if *any* loss has ever occurred in the term's history (`lastGaugeLoss > 0`), the condition will evaluate to true and set `slashed = true` for every user.
- Impact: Any user who stakes in a gauge *after* a loss has occurred will be instantly and unfairly slashed the next time `getRewards` is triggered (e.g., during `unstake`, `stake`, or `updateMintRatio`). Their entire CREDIT stake will be permanently lost and their GUILD rewards wiped out, as their balance is reset to zero.
