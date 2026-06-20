# Audit: 2024-05-loop

## Untracked ETH can be swept by unrelated claimants
- Location: `src/PrelaunchPoints.sol` : `_claim`, `receive`, `convertAllETH`
- Mechanism: The contract accepts raw ETH through `receive()` without crediting it to any user or increasing `totalSupply`. Later, ETH is consumed using whole-contract balance snapshots instead of claim-local deltas. `convertAllETH()` deposits `address(this).balance`, distributing any pre-existing untracked ETH across ETH stakers. More critically, non-ETH `_claim()` calls `_fillQuote()` and then sets `claimedAmount = address(this).balance`, so a token claimer receives all ETH currently in the contract, not only ETH produced by their swap. Because `_percentage` may be `0`, a user with any nonzero token balance can attempt a zero-amount claim and sweep stray ETH without consuming their locked tokens.
- Impact: Any ETH accidentally or forcibly sent to the contract after ETH conversion can be captured by the first non-ETH claimer and minted as lpETH to themselves. ETH sent before conversion is also misallocated to ETH stakers rather than the sender or a recovery path. This is an accounting flaw around untracked ETH balances.

