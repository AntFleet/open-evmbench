# Audit: 2025-01-next-generation

I analyzed both reports for overlap. The two reports cover entirely disjoint code paths — Report A covers fee/allowance accounting, initializers, the safety switch, master-minter events, and fee-rate validation; Report B covers a single `forceTransfer` mint/burn issue in `ERC20AdminUpgradeable.sol`. No finding in A describes the same root cause and code path as B's finding, so there are **no consensus findings**. All six findings are single-reviewer.

Here is the merged report.

---

# Merged Security Audit Report — EURF Token

## Consensus findings

*None.* The two reports describe entirely disjoint root causes and code paths — there is no finding present in both. All findings below are reported by a single reviewer.

---

## Additional findings (single-reviewer)

## Transaction fee is debited outside the ERC-20 allowance (and beyond the signed value)
*(Reviewer A only)*
- Location: `Token.sol` : `transferFrom` and `transferWithAuthorization` → `transferSanity` → `_payTxFee` (`_payTxFee` does `_update(from, _feesFaucet, txFees)`); `FeesHandlerUpgradeable.sol` : `calculateTxFee`.
- Mechanism: `transferFrom(sender, recipient, amount)` first calls `transferSanity(sender, recipient, amount)`, which calls `_payTxFee(sender, amount)` and moves `txFees` directly out of `sender` via `_update`, **before** `super.transferFrom` runs `_spendAllowance(sender, spender, amount)`. The allowance is only ever decremented by `amount`, never by `txFees`, so the fee debit completely bypasses the approval accounting. The same pattern applies in `transferWithAuthorization`, where the holder's EIP-712 signature authorizes `value`, but `_payTxFee` debits `txFees` on top, so the holder loses `value + txFees` while signing only for `value`.
- Impact: An approved spender can cause the token owner to be debited more than the approved allowance (`amount + txFees` leaves the owner's balance while only `amount` is charged against the allowance). This breaks the core ERC-20 invariant that a `transferFrom` removes at most `allowance` from the owner, and breaks integrations that approve exact amounts. The over-debit is bounded by the fee on the allowance and routed to `_feesFaucet` (the spender does not directly profit), but it is an unauthorized debit of owner funds. For `transferWithAuthorization`, the signer pays more than the value they authorized.

## Front-runnable / unprotected initializers
*(Reviewer A only)*
- Location: `Token.sol` : `initialize()`; `Forwarder.sol` : `initialize(address)`.
- Mechanism: `EURFToken.initialize()` grants `OWNER`/`DEFAULT_ADMIN_ROLE` to `msg.sender` and is only protected by the `initializer` modifier (first-caller-wins). The implementation is protected by `constructor() initializer {}`, but the **proxy's** `initialize()` is not bound to the deployer; if deployment and initialization are not performed atomically (single tx / proxy constructor), an attacker can front-run `initialize()` and become `OWNER`. `Forwarder` is worse: it is upgradeable (`OwnableUpgradeable`, `initializer`) but its constructor does **not** call `_disableInitializers()`, so the implementation itself is freely initializable, and the proxy `initialize` is likewise first-caller-wins.
- Impact: If init is non-atomic, an attacker who wins the race becomes `OWNER` of `EURFToken`. `OWNER` is `_authorizeUpgrade`'s gate (UUPS), so this yields full upgrade control and effective drain/seizure of all funds — critical, conditional on deployment practice. For the Forwarder, the missing `_disableInitializers()` lets anyone initialize the implementation and become its owner (lower impact since the forwarder is not UUPS, but still an ownership-takeover gap).

## `safetySwitch` lets a removed controller re-enable operations
*(Reviewer A only)*
- Location: `ERC20ControlerMinterUpgradeable.sol` : `safetySwitch()` (the `else` / re-enable branch).
- Mechanism: When a `CONTROLLER` disables operations, `_operatingController` is set to that controller's address. The re-enable branch authorizes via `hasRole(DEFAULT_ADMIN_ROLE, sender) || _operatingController == sender` — i.e., it checks a stored address rather than the *current* `CONTROLLER` role. If that controller is subsequently revoked with `removeController` (e.g., because it is compromised), it still satisfies `_operatingController == sender` and can flip operations back on.
- Impact: A removed/rogue controller can override the safety pause that was set during an incident, re-enabling mint/burn against the operator's intent. The window is limited (an admin re-enable resets `_operatingController` to `address(0)`, and re-enabling consumes the stored address), but it is a genuine access-control inconsistency: re-enabling should be gated on the live role, not a retained address.

## `setMasterMinter` emits a max-allowance event that is never written to storage
*(Reviewer A only)*
- Location: `ERC20ControlerMinterUpgradeable.sol` : `setMasterMinter`.
- Mechanism: The function emits `MinterAllowanceUpdated(newMasterMinter, type(uint256).max)` but never writes `minterAllowed[newMasterMinter] = type(uint256).max`. On-chain, `getMinterAllowance(newMasterMinter)` returns `0`, contradicting the emitted event. (Functionally the master minter mints without consulting `minterAllowed`, so on-chain behavior is unaffected.)
- Impact: Event-vs-storage desync. Off-chain indexers/monitoring relying on `MinterAllowanceUpdated` will record an "infinite" allowance for the master minter that does not exist in storage, which can mislead accounting/risk dashboards. No direct on-chain exploit, but a real data-integrity defect.

## `setTxFeeRate` admits a 100% fee
*(Reviewer A only)*
- Location: `FeesHandlerUpgradeable.sol` : `setTxFeeRate` (`if (newTxFeeRate > FEE_RATIO ...)` — `FEE_RATIO == 10000`).
- Mechanism: The upper bound permits `newTxFeeRate == FEE_RATIO` (100%). Because the fee is charged *on top* of the transferred amount, a 100% rate makes every transfer require `2 * amount` of balance and send an amount equal to the transfer to `_feesFaucet`. The `newTxFeeRate < 0` clause is dead code (unsigned).
- Impact: ADMIN-gated, so it requires a malicious or compromised admin, but it is a configuration-validation gap that lets a single role effectively double transfer cost / render normal transfers economically broken without any second check. Lower severity due to the trust gate, but a setter that accepts the boundary "100%" value.

## `forceTransfer` can mint or burn by passing the zero address
*(Reviewer B only)*
- Location: `contracts/ERC20AdminUpgradeable.sol` : `forceTransfer` / `adminSanity` (around lines 67-82).
- Mechanism: `forceTransfer` calls OpenZeppelin's internal `_update(from, to, amount)` directly. In OZ ERC20 v5, `_update(address(0), to, amount)` mints and `_update(from, address(0), amount)` burns. `adminSanity` rejects transfers to the token contract and blacklisted recipients, but it does not reject `from == address(0)` or `to == address(0)`.
- Impact: Any account with `ADMIN` can bypass the dedicated minter/burner controls, minter allowances, and the `_operating` safety switch by calling `forceTransfer(address(0), recipient, amount)` to mint unlimited tokens, or `forceTransfer(victim, address(0), amount)` to burn user funds. This is a role-bound privilege escalation: it requires `ADMIN`, but breaks the intended separation between transfer administration and supply control.

