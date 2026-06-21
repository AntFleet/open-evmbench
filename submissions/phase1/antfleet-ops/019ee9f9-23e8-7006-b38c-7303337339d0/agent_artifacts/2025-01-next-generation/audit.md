# Audit: 2025-01-next-generation

# Security Audit Report: EURF Token System

Audit scope: the six contracts you provided (`ERC20AdminUpgradeable`, `ERC20ControlerMinterUpgradeable`, `ERC20MetaTxUpgradeable`, `FeesHandlerUpgradeable`, `Forwarder`, `EURFToken`). Findings below are limited to genuine security/logic flaws.

---

## Mint and burn bypass emergency pause
- **Location:** `ERC20ControlerMinterUpgradeable.sol` : `mint`, `burn`; `EURFToken.sol` : (inherited, not overridden)
- **Mechanism:** `pause()` only affects paths that go through `adminSanity()` (transfers). `mint()` and `burn()` never call `adminSanity()` or `paused()`, and only check `_operating`. A paused token can still have its supply changed by any `MINTER_ROLE` / `MASTER_MINTER` holder.
- **Impact:** During an emergency pause intended to freeze all token movement, a compromised or malicious minter can still mint new tokens (inflation) or burn their balance. Pause does not fully halt token state changes.

---

## Mint bypasses recipient blacklist
- **Location:** `ERC20ControlerMinterUpgradeable.sol` : `mint`; `EURFToken.sol` : (inherited, not overridden)
- **Mechanism:** All transfer paths in `EURFToken` call `adminSanity()`, which reverts if `to` is blacklisted. `mint()` calls `_mint(to, amount)` directly with no blacklist or `adminSanity()` check on `to`.
- **Impact:** A minter can credit tokens to a blacklisted address, defeating blacklist enforcement for inbound value. Compliance seizure via `forceTransfer` (which cannot send *to* blacklisted addresses) can be partially undone by minting back to that address, or blacklisted entities can still receive funds through minting.

---

## Fee balance check without fee collection when faucet unset
- **Location:** `EURFToken.sol` : `_payTxFee`
- **Mechanism:** When `_txfeeRate > 0`, `_payTxFee` requires `balanceOf(from) >= txAmount + txFees`, but only transfers `txFees` if `_feesFaucet != address(0)`. If the fee faucet was never set, was zeroed, or misconfigured, the contract still enforces the higher balance requirement without moving or burning the fee tokens.
- **Impact:** Users cannot transfer their full balance (or near-full balance) even though no fee is actually collected — effective denial of service on transfers whenever `txFeeRate > 0` and `_feesFaucet == address(0)`. A user with exactly `amount` tokens cannot transfer `amount` at all.

---

## Transfer fees taken from sender beyond ERC-20 allowance
- **Location:** `EURFToken.sol` : `transferFrom` (also affects `permit` → `transferFrom` flows)
- **Mechanism:** `transferSanity()` deducts `calculateTxFee(amount)` from `sender` via `_payTxFee` *before* `super.transferFrom()` runs. OpenZeppelin’s `transferFrom` only consumes allowance for `amount`, not `amount + fee`. The fee is an additional debit from the sender’s balance, outside the approved spending cap.
- **Impact:** A spender approved for `N` tokens can cause the holder to lose `N + fee` tokens in a single `transferFrom`, with only `N` covered by allowance. Integrators, DEX routers, and users who size approvals tightly (common pattern) can suffer unexpected balance loss or failed transactions. A malicious spender can grief holders who approved exact amounts.

---

## Safety switch does not halt transfers
- **Location:** `ERC20ControlerMinterUpgradeable.sol` : `safetySwitch`, `mint`, `burn`; `EURFToken.sol` : `transfer`, `transferFrom`, `transferWithAuthorization`
- **Mechanism:** `_operating` gates only `mint()` and `burn()`. Transfer functions never read `_operating`; they only use `adminSanity()` (pause/blacklist). A `CONTROLLER` can disable mint/burn but transfers—including `transferWithAuthorization` and meta-tx transfers via the trusted forwarder—continue unaffected.
- **Impact:** A compromised controller cannot stop secondary-market transfers, only primary issuance/redemption via mint/burn. Conversely, `ADMIN` pause cannot stop minting. Emergency controls are split and can be circumvented depending on which role is compromised; neither role alone provides a full circuit breaker.

---

## `payGaslessBasefee` callable by trusted forwarder without payer authorization in call data
- **Location:** `EURFToken.sol` : `payGaslessBasefee`; `Forwarder.sol` : `execute`
- **Mechanism:** `payGaslessBasefee(payer, paymaster)` only checks `msg.sender == trustedForwarder`. It does not verify a payer signature for the base-fee payment. In the provided `Forwarder`, the only call path passes `req.from` as `payer`, and `req.from` is signature-bound in `execute()`. However, the **token** trusts *any* call from the forwarder address with arbitrary `(payer, paymaster)` arguments.
- **Impact:** If the trusted forwarder is upgraded, replaced, compromised, or a second vulnerable entry point is added to that contract, an attacker can drain `_gaslessBasefee` per call from any holder with sufficient balance, without a payer-signed authorization on the token. The token’s security is fully coupled to forwarder implementation correctness forever.

---

## ERC-2771 meta-tx sender extraction without calldata length guard
- **Location:** `ERC20MetaTxUpgradeable.sol` : `_msgSender`
- **Mechanism:** When `msg.sender` is the trusted forwarder, `_msgSender()` reads the last 20 bytes of calldata via inline assembly without checking `msg.data.length >= 20`. OpenZeppelin’s `ERC2771Context` includes this guard for a reason: short calldata can cause the “sender” to be derived from the function selector or zero-padding.
- **Impact:** A buggy or malicious trusted forwarder that invokes the token with truncated calldata can cause `_msgSender()` to resolve to an attacker-chosen or zero address. That could let an attacker transfer/blacklist-check/fee-charge against the wrong account, or impersonate a victim on fee-bearing transfers. Exploitability depends on forwarder behavior, but the token lacks a standard safety check.

---

## `transferWithAuthorization` charges fees before signature validation (griefing / nonce consumption ordering)
- **Location:** `EURFToken.sol` : `transferWithAuthorization`
- **Mechanism:** The override runs `transferSanity(holder, spender, value)` (pause/blacklist/fee deduction) before `super.transferWithAuthorization()` validates the EIP-712 signature and consumes the nonce. State changes in `transferSanity` are rolled back on revert, so this is not a permanent drain—but any caller can trigger fee-path logic and balance checks on behalf of `holder` before signature failure is detected.
- **Impact:** Limited on-chain impact due to atomic revert, but relayers can force repeated pre-validation work. More importantly, if `_payTxFee` or future hooks in `transferSanity` ever become stateful across reentrancy, this ordering violates checks-effects-interactions. Safer pattern is verify signature first, then apply fees.

---

## Uninitialized proxy initialization front-running
- **Location:** `EURFToken.sol` : `initialize`; `Forwarder.sol` : `initialize`
- **Mechanism:** Both `initialize()` functions are `public` with the `initializer` modifier but no access control on the initializer caller. If a proxy is deployed without atomically calling `initialize` in the same transaction, any address can call `initialize()` first.
- **Impact:** On `EURFToken`, the frontrunner becomes `DEFAULT_ADMIN_ROLE` / owner and controls upgrades, roles, fees, and forwarder. On `Forwarder`, the frontrunner becomes owner and can register request types. Full protocol takeover on careless deployment.

---

## `setAdministrator` allows zero address
- **Location:** `ERC20AdminUpgradeable.sol` : `setAdministrator`
- **Mechanism:** `setOwner` in `EURFToken` rejects `address(0)`, but `setAdministrator` has no zero-address validation before `grantRole(ADMIN, newAdmin)`.
- **Impact:** A mistaken or malicious `DEFAULT_ADMIN_ROLE` call can assign `ADMIN` to `address(0)`, bricking all `ADMIN`-gated operations (`pause`, `blacklist`, `forceTransfer`, `setTrustedForwarder`, fee config) until a new admin is granted via raw `grantRole` by `DEFAULT_ADMIN_ROLE`.

---

## Parent contracts lack storage gaps (upgrade storage collision risk)
- **Location:** `ERC20AdminUpgradeable.sol`, `ERC20ControlerMinterUpgradeable.sol`, `ERC20MetaTxUpgradeable.sol`, `FeesHandlerUpgradeable.sol`
- **Mechanism:** Only `EURFToken` declares `uint256[49] private __gap`. Parent upgradeable contracts add state variables (`_blacklist`, `minterAllowed`, `_trustedForwarder`, `_feesFaucet`, etc.) without gaps. Future versions that insert variables into parents will shift storage for the entire inheritance tree.
- **Impact:** A UUPS upgrade that modifies parent contract layouts can corrupt balances, roles, fees, blacklist state, or nonces — potentially bricking the token or enabling privilege escalation. This is a classic upgradeable-contract vulnerability.

---

## `forceTransfer` allows ADMIN to seize tokens from blacklisted addresses (centralization / policy)
- **Location:** `ERC20AdminUpgradeable.sol` : `adminSanity`, `forceTransfer`
- **Mechanism:** When `msg.sender` has `ADMIN`, `adminSanity` skips the sender-blacklist and pause checks for the `from` address. `forceTransfer` then moves tokens via `_update` without spending allowance.
- **Impact:** Not a logic bug if intentional compliance design, but any `ADMIN` key compromise allows seizure of any account’s tokens (including blacklisted users), bypassing pause. Worth treating as a **trusted-admin risk** with maximum impact: total balance confiscation.

---

## `MASTER_MINTER` can mint without allowance cap
- **Location:** `ERC20ControlerMinterUpgradeable.sol` : `mint`
- **Mechanism:** The `minterAllowed` decrement applies only when the caller has `MINTER_ROLE`. `MASTER_MINTER` bypasses allowance accounting entirely and can mint arbitrary amounts whenever `_operating == true`.
- **Impact:** Compromised `MASTER_MINTER` (or `DEFAULT_ADMIN_ROLE`, which controls that role) can inflate supply without limit. Expected for admin minter, but impact is unbounded minting.

---

# Summary Table

| Severity | Count | Themes |
|----------|-------|--------|
| High     | 3     | Pause/blacklist bypass via mint; broken fee logic (DoS); allowance vs. fees mismatch |
| Medium   | 4     | Split emergency controls; forwarder trust boundary; ERC-2771 calldata guard; init front-run |
| Low/Admin| 3     | Zero admin address; storage gaps on upgrade; privileged seizure/mint centralization |

---

# Not reported (reviewed and excluded)

- **Missing `onlyRole` on `addController` / `addMinter` / `setMasterMinter`:** These call OpenZeppelin `grantRole` / `revokeRole`, which enforce role admins (`DEFAULT_ADMIN_ROLE` for `CONTROLLER`/`MASTER_MINTER`, `MASTER_MINTER` for `MINTER_ROLE`). Not permissionless.
- **Reentrancy in transfers/fees:** Standard ERC-20 `_update` has no external callbacks; no exploitable reentrancy found in the provided code.
- **Forwarder signature replay:** Nonce per `from` is enforced in `execute()`.
- **Gas/style notes:** Excluded per your instructions.

---

# Recommended remediation priorities

1. Route `mint`/`burn` through `adminSanity()` (or explicit pause + blacklist checks).
2. Fix `_payTxFee`: either always collect/burn fees, or skip the balance requirement when `_feesFaucet == address(0)`.
3. Include fees in allowance spending logic, or document and enforce `approve(amount + fee)` at the protocol level.
4. Unify emergency stops (`pause` and `_operating`) or clearly document orthogonal scopes.
5. Add `msg.data.length >= 20` in `_msgSender`, payer-signed authorization for `payGaslessBasefee`, and atomic `initialize` in deployment scripts.
6. Add `__gap` arrays to all upgradeable parents; use `reinitializer` discipline for upgrades.

I’m in **Ask mode**, so this is analysis only. Switch to Agent mode if you want patches or tests written against these findings.

