# Audit: 2024-05-loop

**## Incorrect ETH balance accounting in non-ETH claims**
- Location: `src/PrelaunchPoints.sol` : `_claim`
- Mechanism: `_claim` (for `_token != ETH`) unconditionally does `claimedAmount = address(this).balance` after `_fillQuote` and passes it to `lpETH.deposit`. The contract can hold ETH from prior WETH withdrawals in `lock`, direct `receive()` sends, or any ETH not yet consumed by `convertAllETH`. The comment claiming "there should not be any ETH" is not enforced.
- Impact: A user claiming a non-ETH token after `convertAllETH` can receive more lpETH than the amount produced by their swap (stealing ETH belonging to ETH lockers or the protocol).

**## Swap validation can be bypassed via malformed 0x calldata**
- Location: `src/PrelaunchPoints.sol` : `_validateData`, `_decodeUniswapV3Data`, `_decodeTransformERC20Data`, `_claim`
- Mechanism: The assembly decoders read fixed offsets (`p+128`, `p+length+108`, etc.) without verifying calldata length, selector arguments, or path encoding. `_validateData` only checks a few fields (input token, amount, recipient != attacker, output == WETH/ETH) and then forwards the raw `_data` to `exchangeProxy.call`.
- Impact: An attacker can craft calldata that passes the checks but executes a swap that sends tokens/ETH elsewhere, drains the contract, or swaps at 0 minOut, allowing theft of user-locked tokens or ETH.

**## `setLoopAddresses` can be called multiple times, shortening the lock window**
- Location: `src/PrelaunchPoints.sol` : `setLoopAddresses`
- Mechanism: The function has only the `onlyBeforeDate(loopActivation)` modifier and unconditionally does `loopActivation = uint32(block.timestamp)`. Nothing prevents the owner from calling it repeatedly while still before the original 120-day deadline.
- Impact: Owner can prematurely disable all further locking (and force early `convertAllETH` eligibility) by calling the function again after the first call.

**## Missing check allows withdrawal of ETH after `startClaimDate` in emergency mode**
- Location: `src/PrelaunchPoints.sol` : `withdraw`
- Mechanism: The `if (block.timestamp >= startClaimDate) revert UseClaimInstead();` guard for ETH is inside the `else` branch that only runs when `!emergencyMode`. In emergency mode the date check is skipped entirely for every token, including ETH.
- Impact: In emergency mode an ETH locker can bypass `claim` (and the proportional `totalLpETH` distribution) and withdraw raw ETH instead.

**## No slippage / output-amount validation on swaps**
- Location: `src/PrelaunchPoints.sol` : `_fillQuote`, `_validateData`
- Mechanism: `_validateData` decodes neither `minBuyAmount` nor any output amount field; `_fillQuote` only records the delta in `address(this).balance` after the call.
- Impact: A malicious or front-run 0x quote can return far less ETH than expected for a user's locked tokens, resulting in permanent loss of value for the claimer.
