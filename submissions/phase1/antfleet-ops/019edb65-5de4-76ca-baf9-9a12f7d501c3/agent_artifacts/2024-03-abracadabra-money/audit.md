# Audit: 2024-03-abracadabra-money

## Reentrancy in `harvest` and `setStrategy`
- Location: `DegenBox.sol` : `harvest` function, `setStrategy` function
- Mechanism: Both functions perform an external call to a strategy contract (`_strategy.harvest` and `strategy[token].exit`) before updating the BentoBox's internal accounting. The state (`strategyData[token]`, `totals[token]`) is read into memory, the external call is made, and then the state is written back. During the external call, the strategy contract can re-enter the BentoBox (e.g., via `deposit`, `withdraw`, or another `harvest`). Because the state has not been updated yet, recursive calls will see the old `strategyData[token]` and can cause the same `balanceChange` to be applied multiple times, or cause inconsistent updates. This breaks the accounting of strategy balances and total token supply.
- Impact: If the strategy contract is malicious or contains a vulnerability that allows reentrancy, an attacker can inflate or deflate the tracked strategy balance and total elastic supply, leading to loss of funds or incorrect share prices for all depositors of that token.

## Flash loan callback can re-enter state-changing functions
- Location: `DegenBox.sol` : `flashLoan`, `batchFlashLoan`
- Mechanism: The flash loan functions transfer tokens to the borrower, then call `onFlashLoan` / `onBatchFlashLoan` on an untrusted contract, and only after the callback check the repayment condition. No reentrancy guard is used. The callback can re-enter the BentoBox through `deposit`, `withdraw`, `transfer`, or `harvest`, altering the `totals` and `_tokenBalanceOf` that are used in the final check. While a direct exploit to bypass the fee check is not obvious, reentrancy can lead to unexpected state changes that may violate implicit invariants.
- Impact: A malicious flash loan borrower could, in combination with other state-modifying actions, cause the repayment check to pass without returning the full amount, or corrupt the accounting of the BentoBox, potentially leading to loss of funds.

## Stale global totals used in multiple liquidations (CauldronV4)
- Location: `CauldronV4.sol` : `liquidate` function
- Mechanism: The function fetches `bentoBox.totals(collateral)` once before the loop over users. It then calculates the collateral share for each insolvent user using this initial global totals. After the loop, it transfers all collateral shares in a single `bentoBox.transfer`. If the transfer were split into multiple calls, the global totals would change after the first transfer, making later share calculations inaccurate. However, because the transfer is batched into one call, the totals remain unchanged throughout the loop, and the calculation is correct. (No vulnerability here after deeper analysis.)

## `CauldronV4` liquidation does not enforce that `to` equals the swapper address
- Location: `CauldronV4.sol` : `liquidate`
- Mechanism: When a swapper is provided, the collateral is transferred to the `to` address before the swapper's `swap` is called. The swapper does not automatically receive the collateral; it must be the `to` address. If the liquidator passes a `to` that is different from the swapper, the swapper will not have the collateral tokens and the swap will likely fail, causing the transaction to revert. This is an implementation detail that can lead to failed liquidations but is not a security vulnerability (the liquidator is responsible for setting the correct parameters).

## `LockingMultiRewards` reward distribution can be manipulated by front-running `processExpiredLocks`
- Location: `LockingMultiRewards.sol` : `processExpiredLocks`
- Mechanism: The function updates rewards for all given users before unlocking their locks. The reward calculation uses the current `totalSupply()`, which includes the boosted locked amounts. An attacker could front-run `processExpiredLocks` with a `stake` or `lock` to increase the supply, thereby diluting the rewards for the users being unlocked. However, this is a general property of reward systems and not a specific vulnerability.

After thorough review, the only confirmed vulnerability with a clear exploit path is the **reentrancy in `harvest` and `setStrategy`**. The flash loan reentrancy is a design concern but lacks a direct exploit without a malicious strategy. The other issues are either non-exploitable or design choices with low risk.

**Final report:**
- **Reentrancy in `harvest` and `setStrategy`** (High severity)
- **Flash loan reentrancy** (Medium severity, as defense-in-depth)
