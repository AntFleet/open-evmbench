# Audit: 2024-03-gitcoin

# Audit Findings

## `userTotalStaked` not restored on release — released funds are permanently trapped
- Location: `IdentityStaking.sol` : `release`
- Mechanism: When a slash occurs, both `stake.amount` and `userTotalStaked[staker]` are decremented by the slashed amount. When a release occurs, `stake.amount` is incremented by `amountToRelease` but `userTotalStaked[staker]` is **never** incremented. Because withdrawals (`withdrawSelfStake` / `withdrawCommunityStake`) unconditionally decrement `userTotalStaked[msg.sender] -= amount`, any attempt to withdraw the released portion will cause an arithmetic underflow revert once the withdrawal amount exceeds the (now understated) `userTotalStaked`. Example: user stakes 100, is slashed 50 (`amount`=50, `userTotalStaked`=50), then 50 is released (`amount`=100, `userTotalStaked` still 50). Withdrawing 100 decrements `userTotalStaked` by 100 → underflow → revert. The user can withdraw at most 50, and the remaining 50 is permanently locked in the contract. Additionally, any external consumer reading `userTotalStaked` receives an understated value after a release, breaking the interface contract.
- Impact: Released slashed funds can never be withdrawn by the staker; they are permanently stuck in the contract. Downstream systems relying on `userTotalStaked` will read incorrect (understated) values for any user who has had a slash released.

---

## Integer overflow in slash calculation prevents slashing large stakes
- Location: `IdentityStaking.sol` : `slash` (both the self-staker and community-staker loops)
- Mechanism: The slash amount is computed as `uint88 slashedAmount = (percent * stake.amount) / 100;`. Both `percent` (max 100) and `stake.amount` (up to ~3×10²⁶, the uint88 max) are `uint88`, so the multiplication is performed in `uint88` arithmetic. The intermediate product `percent * amount` can be up to `100 × 3.09×10²⁶ ≈ 3.09×10²⁸`, which far exceeds `2⁸⁸ - 1 ≈ 3.09×10²⁶`. In Solidity 0.8.x this overflows and reverts. Concretely, any stake larger than ~3.09M GTC (≈3.09×10²⁴) cannot be slashed at 100%, and any stake larger than ~77.3M GTC cannot be slashed even at 4%. Since GTC's total supply is 100M, a single whale staking a large portion of supply becomes effectively un-slashable at meaningful percentages.
- Impact: A staker who deposits a sufficiently large amount becomes immune to slashing (at high percentages) because every slash attempt reverts. This undermines the core slashing mechanism of the protocol. The fix is to widen the multiplication to `uint256` before dividing: `uint88 slashedAmount = uint88((uint256(percent) * uint256(stake.amount)) / 100);`.
