# Audit: 2024-05-loop

# Audit Report: PrelaunchPoints

## Residual ETH captured by non-ETH claims via `address(this).balance`
- Location: `PrelaunchPoints.sol` : `_claim`
- Mechanism: For non-ETH token claims, after the 0x swap the contract sets `claimedAmount = address(this).balance` and deposits that full balance into lpETH for the caller. It does **not** isolate the swap output (the delta that `_fillQuote` already computes into `boughtETHAmount` but only emits in an event). The contract has a `receive()` function that accepts arbitrary ETH at any time. After `convertAllETH` drains the contract's ETH to lpETH, any ETH subsequently sent via `receive()` (directly, by mistake, or by any other path) sits in the contract. The very next non-ETH token staker who calls `claim` will capture that residual ETH as bonus lpETH, stealing it. The NatSpec on `receive()` even states "ETH sent to this contract directly will be locked forever," but the implementation contradicts this — the ETH is not locked, it is stealable by any non-ETH staker.
- Impact: Any ETH that enters the contract after `convertAllETH` (e.g., accidental transfers to `receive()`, refunds from a swap, or ETH stuck from a failed/reverted lpETH deposit in a prior claim) is stolen by the first non-ETH claimer. The attacker only needs a non-zero balance of any allowed token and can claim with a minimal `_percentage` to sweep the entire residual ETH balance as lpETH.

---

## `_validateData` skips recipient validation for TransformERC20
- Location: `PrelaunchPoints.sol` : `_validateData` / `_decodeTransformERC20Data`
- Mechanism: For `Exchange.TransformERC20`, `_decodeTransformERC20Data` returns only `(inputToken, outputToken, inputTokenAmount, selector)` — it never extracts a `recipient`. The `recipient` local variable in `_validateData` therefore remains `address(0)` (default), and the check `if (recipient != address(this) && recipient != address(0))` always passes. For `UniswapV3` the recipient is properly decoded and validated, but for `TransformERC20` the recipient validation is entirely bypassed. If the 0x `transformERC20` flow (or a transformation embedded in its `transformations` bytes) routes the output token to an address other than this contract, the contract's validation would not catch it.
- Impact: A user (or a malicious party crafting swap data for a victim via approval/signature) could supply TransformERC20 swap data that sends the swapped output to an attacker-controlled address rather than to this contract. The user's token balance is still decremented and the tokens are still pulled and sold, but `address(this).balance` would not increase (or would only capture residual ETH), so the user receives little or no lpETH while the swap output is diverted.

---

## `_fillQuote` uses raw `approve` instead of `SafeERC20`, failing for non-standard tokens
- Location: `PrelaunchPoints.sol` : `_fillQuote`
- Mechanism: `_fillQuote` calls `require(_sellToken.approve(exchangeProxy, _amount))`. The contract uses `SafeERC20` for transfers elsewhere but not here. Some ERC20 tokens (e.g., USDT) do not return a `bool` from `approve`; in Solidity 0.8.20 the ABI decoder will revert when the return data does not match the expected `bool`, causing the swap (and thus the claim) to always fail for such tokens. Additionally, the approval is never reset to zero after the swap, so if a swap is partially filled the exchange proxy retains a dangling allowance.
- Impact: Any allowed token whose `approve` does not return `bool` becomes unclaimable — users' locked tokens are permanently stuck since `claim` always reverts for that token. The dangling allowance on partial fills could allow a compromised exchange proxy to drain un-swapped tokens from the contract later.

---

## `claimAndStake` stakes to `msg.sender` but `_claim` credits/withdraws from `msg.sender` — vault reentrancy can grief
- Location: `PrelaunchPoints.sol` : `claimAndStake` / `_claim`
- Mechanism: `claimAndStake` calls `_claim(_token, address(this), …)` then `lpETHVault.stake(claimedAmount, msg.sender)`. For the ETH path, `_claim` transfers lpETH to `address(this)` using `safeTransfer` (no callback), then the contract approves and calls `lpETHVault.stake`. The `stake` call is an external call to the vault with `msg.sender` as the receiver. If the vault implementation calls back on `msg.sender` (e.g., `onStake` hook), `msg.sender` could reenter `claim` or `claimAndStake`. For the ETH path the balance is already zeroed so reentrant `claim` hits `NothingToClaim`, but a reentrant `withdraw` (if within the withdrawal window) or `lock`/`lockFor` could be used to manipulate state. While the contract follows checks-effects-interactions for the balance update, the interaction with an arbitrary vault whose behavior is only constrained by the `ILpETHVault` interface introduces an untrusted callback path.
- Impact: If `lpETHVault.stake` reenters the caller, an attacker contract receiving the stake callback could reenter `PrelaunchPoints` to perform additional operations during the window where lpETH has been transferred to the contract but not yet staked, or to front-run the stake with other operations. The practical exploitability depends on the vault implementation, but the code does not guard against vault reentrancy.
