# Audit: 2024-05-loop

# Security Audit Report: PrelaunchPoints

---

## ETH dust from `receive()` can be claimed by subsequent users
- **Location:** `PrelaunchPoints.sol` : `_claim` (non-ETH branch)
- **Mechanism:** The `receive()` function intentionally accepts arbitrary ETH transfers (with a comment stating such ETH "will be locked forever"). However, in the non-ETH branch of `_claim`, the received amount is computed as `claimedAmount = address(this).balance` *after* the 0x swap. This balance includes any ETH that was sitting in the contract from a prior direct transfer via `receive()`, a previous failed `lpETH.deposit`, or any other source. As a result, the next user to call `claim`/`claimAndStake` for a non-ETH token sweeps up all of this "dust" and deposits it into `lpETH` in their own favor. The user whose tokens funded the swap effectively subsidizes the claimer.
- **Impact:** Anyone can monitor the mempool/contract and front-run a claim transaction to donate a small amount of ETH via `receive()`, then call `claim` themselves to capture not only the swapped ETH but any pre-existing balance as lpETH. More importantly, any user who accidentally sends ETH to the contract (e.g., misdirected transfers) will have those funds stolen by the next claimer rather than being permanently locked as the comment suggests.

---

## Integer underflow in `convertAllETH` blocks the primary happy path
- **Location:** `PrelaunchPoints.sol` : `convertAllETH`
- **Mechanism:** The guard `if (block.timestamp - loopActivation <= TIMELOCK)` performs an unsigned subtraction. In the constructor, `loopActivation` is set to `block.timestamp + 120 days`. If the owner never calls `setLoopAddresses` (which would update `loopActivation` to the current block timestamp), then `loopActivation` remains far in the future, and the subtraction `block.timestamp - loopActivation` underflows. Solidity 0.8 reverts on underflow, so `convertAllETH` is permanently uncallable. Without `convertAllETH`, `startClaimDate` is never set (it stays at `uint32.max`), so the `onlyAfterDate(startClaimDate)` modifier on `claim`/`claimAndStake` can never be satisfied. The result is that the entire ETH-conversion branch is dead unless `setLoopAddresses` is called first.
- **Impact:** A deployment or operational mistake (failure to call `setLoopAddresses` within 120 days) bricks the core conversion functionality. Users can still call `withdraw` to retrieve their ETH, but the intended lpETH-distribution flow is unreachable. An attacker cannot exploit this for direct theft, but the design leaves the contract in a permanently degraded state with no on-chain recovery beyond user withdrawals.

---

## Loss of funds if `lpETH` or `lpETHVault` is unset/malicious during `claim` of non-ETH tokens
- **Location:** `PrelaunchPoints.sol` : `_claim` (non-ETH branch) and `claimAndStake`
- **Mechanism:** For non-ETH claims, the user's internal balance `balances[msg.sender][_token]` is decremented to `userStake - userClaim` *before* any external interactions (`_fillQuote` to 0x, then `lpETH.deposit`). If the swap succeeds but `lpETH.deposit{value: claimedAmount}(_receiver)` reverts (e.g., the configured `lpETH` address is a non-contract, is paused, or has a faulty `deposit` implementation), the entire transaction reverts — so the user is safe in that specific case. However, if `lpETH.deposit` accepts a zero or near-zero `value` and mints a proportional (or zero) amount of lpETH, the user receives nothing while their internal balance has already been burned. Similarly, in `claimAndStake`, if `lpETHVault.stake` reverts after `_claim` has already moved lpETH into `address(this)`, the lpETH is stranded in the contract (and `recoverERC20` explicitly blocks recovery of `lpETH`).
- **Impact:** Users who call `claim`/`claimAndStake` when the configured loop addresses are misconfigured, paused, or behave non-standardly can permanently lose their locked tokens or have their lpETH trapped in the contract with no recovery path. The contract provides no pre-flight check that `lpETH` and `lpETHVault` are valid, non-zero, functioning contracts, nor a "rescue" mechanism for tokens that have been deducted but not successfully claimed.

---

## No validation of actual ETH received from 0x swap
- **Location:** `PrelaunchPoints.sol` : `_fillQuote` and `_claim`
- **Mechanism:** `_validateData` only checks structural fields of the 0x calldata (selector, input token, input amount, output token, recipient). It does not extract or verify `minBuyAmount`. The contract then calls `_fillQuote`, which uses `address(this).balance - boughtETHAmount` to determine proceeds, but never compares this against any minimum. A user can craft (or have a third party craft) 0x calldata where `minBuyAmount = 0` and route through a path that returns effectively zero ETH (e.g., through an illiquid pool or a pool they control that gives a 1:1→0 trade). Because the user's internal balance is decremented by the full `userClaim` before the swap, the user can be drained of their locked tokens while receiving near-zero lpETH.
- **Impact:** A malicious or careless user can self-harm by submitting swaps with `minBuyAmount = 0`, permanently losing their locked tokens in exchange for nothing. More dangerously, if the 0x API is manipulated, front-run, or if the user is tricked into signing bad calldata, there is no on-chain safeguard. A sandwich attack against the 0x swap is also unmitigated: the attacker can extract value from the swap without the contract noticing.

---

## No two-step ownership transfer; owner can be bricked
- **Location:** `PrelaunchPoints.sol` : `setOwner`
- **Mechanism:** `setOwner` directly writes `owner = _owner` in a single call. There is no pending-owner pattern and no zero-address check. If the owner mistakenly (or maliciously, via a compromised key) sets `owner` to the zero address or to an address they do not control, all `onlyAuthorized` functions become permanently inaccessible. This includes `setLoopAddresses`, `convertAllETH`, `allowToken`, `setEmergencyMode`, and `recoverERC20`.
- **Impact:** A single erroneous `setOwner` transaction bricks the admin surface of the contract. Users would still be able to call `withdraw` (since it lacks `onlyAuthorized`) and could call `claim` once `startClaimDate` is set, but no further governance actions, emergency interventions, or token recoveries would be possible. There is no on-chain way to recover from this state.

---

## Zero-address receiver in `lockETHFor` / `lockFor` permanently locks funds
- **Location:** `PrelaunchPoints.sol` : `lockETHFor`, `lockFor`, `_processLock`
- **Mechanism:** Neither `lockETHFor(_for, ...)` nor `lockFor(_token, _amount, _for, ...)` validates that `_for != address(0)`. The internal `_processLock` writes directly to `balances[_receiver][...]` with no zero-address guard. ETH (or tokens) sent with `_for = address(0)` are credited to a balance that no EOA or contract can ever withdraw from, because all withdraw/claim paths key on `msg.sender` and there is no admin sweep for zero-address balances. Similarly, the `referral` parameter is unconstrained bytes32, but that is a backend issue rather than a fund-loss vector.
- **Impact:** Caller error (or a buggy frontend) can permanently burn user funds by passing `_for = address(0)`. The contract provides no safeguard or event-based alerting for this case.

---

## Reentrancy window in `withdraw` for ETH (mitigated but worth noting)
- **Location:** `PrelaunchPoints.sol` : `withdraw` (ETH branch)
- **Mechanism:** The function uses the checks-effects-interactions pattern (balance zeroed, `totalSupply` decremented) before the low-level `msg.sender.call{value: lockedAmount}("")`. This is correct for same-token reentrancy (the attacker cannot withdraw the same ETH balance twice because it is already zeroed). However, the receiving contract could reenter and call `withdraw` for a *different* token it has locked, or call `claim` for a different token, draining all of its balances in an arbitrary order within a single transaction. There is no global reentrancy guard.
- **Impact:** A malicious receiver contract can be used to atomically sweep all of a user's locked balances across multiple tokens in a single transaction, potentially front-running their own pending transactions or interacting with the 0x swap in `claim` mid-flight. The impact is limited to the user's own funds, so this is not a theft vector against other users, but it does amplify any user-side bug or griefing attack and complicates reasoning about cross-function interactions. A `nonReentrant` modifier on the value-transferring functions would close this cleanly.
