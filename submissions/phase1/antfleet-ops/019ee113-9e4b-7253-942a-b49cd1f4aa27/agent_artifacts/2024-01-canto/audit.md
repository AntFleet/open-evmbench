# Audit: 2024-01-canto

## 1. VotingEscrow contract cannot be deployed (storage array too large)
- Location: `src/VotingEscrow.sol` : state variables `pointHistory` and `userPointHistory`
- Mechanism: `Point[1000000000000000000] public pointHistory;` and `mapping(address => Point[1000000000]) public userPointHistory;` declare fixed-size arrays of 1e18 and 1e9 elements respectively. A `Point` struct occupies 3 storage slots (≈96 bytes). Allocating 1e18 slots requires ≈9.6×10¹⁹ bytes of storage, far exceeding the EVM limit (≈2⁷⁷ slots) and the block gas limit. Deploying the contract will either revert during code execution or run out of gas. The same issue applies to per-user arrays of 1e9 points.
- Impact: The contract is undeployable; the entire system (which depends on VotingEscrow) cannot be brought up. If somehow deployed via a forced path, writing to these mappings would be impossible.

## 2. LendingLedger passes block numbers to a function expecting timestamps
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: `uint256 epoch = (i / BLOCK_EPOCH) * BLOCK_EPOCH;` produces a block number (e.g., 1,000,000). This is forwarded to `gaugeController.gauge_relative_weight_write(_market, epoch)`, but `GaugeController` treats the parameter as a Unix timestamp and does `t = (_time / WEEK) * WEEK` (WEEK = 604,800 seconds). A block number passed as a timestamp floors to a time in 1970 or thereabouts, so the gauge controller finds no historical weight data and returns 0.
- Impact: CANTO rewards (`cantoReward`) are calculated as `… * gauge_relative_weight_write(...) / 1e18`, so the multiplier is effectively zero and no CANTO emissions are ever distributed to lending markets. Secondary rewards (`secRewardsPerShare`) still accrue, but the primary incentive mechanism is broken.

## 3. Integer overflow in `accCantoPerShare`
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: `market.accCantoPerShare += uint128((cantoReward * 1e18) / marketSupply);` casts the result to `uint128`. `cantoReward` can be on the order of `blockDelta * cantoPerBlock[epoch]` (blockDelta ≤ 100,000, cantoPerBlock set by governance), and `(cantoReward * 1e18) / marketSupply` can easily exceed `2¹²⁸-1` when `marketSupply` is small (e.g., 1 wei of cNOTE). For example, 1e20 cantoReward * 1e18 / 1 = 1e38 > 3.4e38 is borderline, and larger values overflow uint128.
- Impact: The accumulator wraps around, causing `accCantoPerShare` to decrease or reset. Users can then claim inflated or incorrect reward amounts, or existing reward debts become detached from the true accumulation, allowing theft of CANTO or griefing.

## 4. `setGovernance` accepts the zero address
- Location: `src/GaugeController.sol` : `setGovernance`; `src/LendingLedger.sol` : `setGovernance`
- Mechanism: Both functions lack a zero-address check. Governance can be set to `address(0)`. Since all admin functions (`add_gauge`, `remove_gauge`, `whiteListLendingMarket`, `setRewards`, `setGovernance`) are gated by `onlyGovernance`, this bricks the contract permanently.
- Impact: An admin mistake or compromise leads to permanent loss of administrative control and the inability to add/remove gauges, whitelist markets, or fix the contract.

## 5. Unbounded loop in `update_market` can DoS reward accounting
- Location: `src/LendingLedger.sol` : `update_market`
- Mechanism: `while (i < block.number)` iterates from `market.lastRewardBlock` to the current block without a hard cap. If the market is inactive for a long time (or never updated), a single call may have to iterate over millions of blocks. Each iteration performs storage reads, an external call to the gauge controller, and accumulator updates. The transaction will exceed the block gas limit and revert.
- Impact: The first caller after a long idle period (or after the first `whiteListLendingMarket`) is forced to process all pending updates. This is a griefing/DOS vector and can stall reward distribution for all users of a market.

## 6. Withdraw is impossible for delegated locks
- Location: `src/VotingEscrow.sol` : `withdraw`
- Mechanism: `require(locked_.delegatee == msg.sender, "Lock delegated");` blocks withdrawal whenever `delegatee != msg.sender`. There is no `undelegate` or `delegate` function in the provided code, but `LockedBalance` tracks `delegated` and `delegatee` and `increaseAmount` already mutates them, implying delegation is intended. Once a lock is delegated (e.g., by a future delegate function or by any code path that sets `delegatee`), the original owner can never call `withdraw`, and the funds are permanently stuck.
- Impact: Loss of user funds if delegation is introduced or accidentally triggered. Even without a public delegate function, the storage layout invites future bugs where `delegatee` is set but never cleared.

## 7. Secondary rewards are not claimable
- Location: `src/LendingLedger.sol` : `claim` and `update_market`
- Mechanism: `update_market` accrues `secRewardsPerShare` for every block regardless of gauge weight, and `sync_ledger` updates `user.secRewardDebt`. However, `claim` only computes and pays `cantoToSend` (CANTO) and never touches `secRewardDebt` or pays out secondary rewards. The state variable silently grows.
- Impact: Secondary rewards are effectively unclaimable; users cannot retrieve them, and the accounting (`secRewardDebt`) becomes dead state. This is at minimum an incomplete implementation; if secondary rewards are tokens, they may be unrecoverable.

## 8. `vote_for_gauge_weights` accepts a trivially large weight range and is vulnerable to power_used underflow
- Location: `src/GaugeController.sol` : `vote_for_gauge_weights`
- Mechanism: `require(_user_weight >= 0 && _user_weight <= 10_000, "Invalid user weight");` is meaningless for a `uint256` (always ≥ 0). More importantly, `power_used = power_used + new_slope.power - old_slope.power;` is unsigned arithmetic. If the user's stored `vote_user_slopes[…].power` is larger than `vote_user_power[msg.sender]` (which can happen if a gauge is removed and the user later votes with 0, or through state corruption from the `Math.max` logic), this underflows and reverts. The `require(power_used >= 0 …)` check is dead code for `uint256`.
- Impact: Legitimate users may be unable to update or withdraw their votes. The check is also insufficient: the real bound is that `power_used + new_slope.power >= old_slope.power`, which is not enforced safely.

## 9. Stale `cantoToSend` can be negative on `claim`
- Location: `src/LendingLedger.sol` : `claim`
- Mechanism: `int256 cantoToSend = accumulatedCanto - user.rewardDebt;` If `user.rewardDebt` was set higher than the current accumulation (possible if `accCantoPerShare` ever decreases due to the uint128 overflow in finding 3, or due to a market re-whitelisting that resets state inconsistently), `cantoToSend` is negative. The `if (cantoToSend > 0)` guard prevents sending, but `user.rewardDebt = accumulatedCanto;` unconditionally reduces the debt. The user silently forfeits the excess.
- Impact: Users can lose accrued rewards when the accumulator resets or overflows. This interacts with finding 3 to amplify the damage from the overflow.

## 10. `_change_gauge_weight` blindly overwrites accumulated bias/slope
- Location: `src/GaugeController.sol` : `_change_gauge_weight`
- Mechanism: `points_weight[_gauge][next_time].bias = _weight;` and `points_sum[next_time].bias = new_sum;` overwrite existing point data for `next_time` without reading or adding. The function is `internal` and currently only called from `add_gauge` with weight 0 (where the existing values are zero), but any future caller (or governance action that re-uses the function) will silently destroy accumulated vote weight for the current week.
- Impact: Loss of gauge weight and corrupted accounting if the function is reused or called with non-zero weight, enabling governance to arbitrarily zero out votes at week boundaries.
