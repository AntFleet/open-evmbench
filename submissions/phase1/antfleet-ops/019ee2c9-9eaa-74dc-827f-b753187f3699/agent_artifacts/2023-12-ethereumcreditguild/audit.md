# Audit: 2023-12-ethereumcreditguild

## Historical term losses let anyone wipe later surplus stakes
- Location: `src/loan/SurplusGuildMinter.sol` : `getRewards`
- Mechanism: `getRewards` computes `slashed` before it loads `userStake` from storage. At that point `userStake.lastGaugeLoss` is still the zero-initialized value of an empty memory struct, so the check effectively becomes `GuildToken.lastGaugeLoss(term) > 0` instead of `term.lastGaugeLoss > storedUserStake.lastGaugeLoss`. As a result, once a term has ever reported a loss, any later stake in that term is treated as slashable even if the user staked after the loss or had already accounted for it. The bad `slashed` result then flows into the end of `getRewards`, which zeroes the stored stake record.
- Impact: Any caller can permissionlessly erase another user’s `SurplusGuildMinter` position by calling `getRewards(victim, term)` after the term has had any historical loss. The victim’s recorded CREDIT stake and minted GUILD position are wiped, `unstake` becomes a no-op because it returns early when `slashed == true`, and the contributed CREDIT remains forfeited in the term surplus buffer.

## Rebasing self-transfers create phantom CREDIT balances and votes
- Location: `src/tokens/ERC20RebaseDistributor.sol` : `transfer`, `transferFrom`
- Mechanism: When `from == to` and the account is rebasing, both the sender-side share reduction path and the receiver-side share increase path run against the same pre-transfer rebasing state. The raw ERC20 balance does not change on a self-transfer, but the code still first computes a reduced share count as if tokens left the account, then overwrites it with an increased share count as if fresh tokens arrived. `totalRebasingShares` is not increased to match. This lets one account inflate its rebasing share ownership without adding tokens.
- Impact: A rebasing CREDIT holder can manufacture phantom `balanceOf` and governance voting power, then use the inflated balance to delegate or vote with CREDIT that does not exist. If there are pending unmaterialized rebase rewards, the attacker can also exit rebase or move funds to realize stolen CREDIT out of `__unmintedRebaseRewards`, draining rewards owed to honest rebasing holders.

## Same-block gauge losses can be bypassed
- Location: `src/tokens/GuildToken.sol` : `notifyGaugeLoss`, `_incrementGaugeWeight`, `applyGaugeLoss`
- Mechanism: Losses are tracked only by `block.timestamp`. When a user with zero existing weight first votes for a gauge, `_incrementGaugeWeight` sets `lastGaugeLossApplied[gauge][user] = block.timestamp`. If one loss is reported, the user joins the gauge later in the same block, and a second loss is reported in that same block, both losses share the same timestamp. `applyGaugeLoss` then sees `lastGaugeLossApplied >= lastGaugeLoss` and refuses to slash the user, even though the user held weight during the later loss.
- Impact: With transaction ordering inside a block, a user can join a lossy gauge between multiple same-gauge loss notifications and escape the burn for the later loss. That preserves GUILD balance and gauge weight that should have been slashed, weakening the protocol’s loss-socialization mechanism.

