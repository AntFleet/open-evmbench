# Audit: 2026-01-tempo-stablecoin-dex

# Security Audit: StablecoinDEX

Findings below are ordered by severity. `MockTIP20.sol` has no exploitable issues in scope (single minter, standard ERC20). All material risk is in `StablecoinDEX.sol`.

---

## Unrestricted `emergencyWithdraw` drains contract funds

- **Location:** `StablecoinDEX.sol` : `emergencyWithdraw` / `_processWithdrawal`
- **Mechanism:** `emergencyWithdraw` calls `_processWithdrawal` with no validation that `msg.sender` has a deposit balance or that `amount` is within it. `_processWithdrawal` subtracts from `balances` inside `unchecked`, so a zero balance underflows to a huge `uint128`, then `safeTransfer` sends real tokens from the contract. There is no `InsufficientBalance` check (unlike `withdraw`).
- **Impact:** Any address can drain all ERC20 balances held by the DEX in one or more calls, without ever depositing. This is a total loss of funds for all LPs and traders.

```solidity
function emergencyWithdraw(address token, uint128 amount) external {
    _processWithdrawal(msg.sender, token, amount);  // no balance check
    emit Withdrawn(msg.sender, token, amount);
}

function _processWithdrawal(...) internal {
    unchecked {
        balances[user][token] -= amount;  // underflows from 0
        totalDeposits[token] -= amount;
    }
    IERC20(token).safeTransfer(user, amount);
}
```

---

## Reentrancy on `withdraw` (CEI violation)

- **Location:** `StablecoinDEX.sol` : `withdraw`
- **Mechanism:** `withdraw` performs the external `safeTransfer` before updating `balances` and `totalDeposits` (violates checks-effects-interactions). On a token with transfer hooks (ERC777-style, or a TIP-20 with policy/hook callbacks), the recipient can reenter `withdraw` while the balance is still credited.
- **Impact:** An attacker can withdraw the same balance multiple times in one transaction and drain more tokens than their internal balance, stealing from other users’ deposits. Risk is real for any callback-capable token the DEX is meant to support.

```solidity
function withdraw(address token, uint128 amount) external {
    // ... balance check ...
    IERC20(token).safeTransfer(msg.sender, amount);  // external call first
    balances[msg.sender][token] -= amount;             // state updated after
    totalDeposits[token] -= amount;
}
```

---

## Missing access control on `cancel`

- **Location:** `StablecoinDEX.sol` : `cancel` / `_cancelOrder`
- **Mechanism:** `cancel` only checks that the order exists (`order.maker != address(0)`). It never requires `msg.sender == order.maker`, even though `Unauthorized` is defined. `_cancelOrder` always refunds `order.remaining` to the maker, so this is not direct theft, but any third party can cancel any open order.
- **Impact:** Attackers can grief market makers by canceling orders at will (DoS on liquidity), disrupt routing/settlement, and manipulate which orders are available to fill—without authorization. Makers lose expected fills and must continuously re-place orders.

```solidity
function cancel(uint128 orderId) external {
    Order storage order = orders[orderId];
    if (order.maker == address(0)) revert OrderDoesNotExist();
    _cancelOrder(orderId, order);  // no require(msg.sender == order.maker)
}
```

---

## Fee-on-transfer / deflationary token accounting mismatch

- **Location:** `StablecoinDEX.sol` : `deposit` / `withdraw`
- **Mechanism:** `deposit` credits `amount` to internal `balances` based on the requested transfer amount, not the contract’s actual balance delta. If a token charges a fee on transfer, the contract receives less than `amount` while the user is credited the full `amount`.
- **Impact:** The first withdrawers can extract more tokens than the contract truly holds; later users cannot withdraw (insolvency). An attacker can deposit fee-on-transfer tokens, inflate internal balance, and withdraw full nominal amounts—stealing value from honest depositors of the same token.

```solidity
IERC20(token).safeTransferFrom(msg.sender, address(this), amount);
balances[msg.sender][token] += amount;  // credits full amount, not received
totalDeposits[token] += amount;
```

---

## Inflated internal balance after `emergencyWithdraw` enables repeated `withdraw`

- **Location:** `StablecoinDEX.sol` : `emergencyWithdraw` + `withdraw`
- **Mechanism:** After one `emergencyWithdraw` call with zero prior balance, `balances[user][token]` underflows to near `type(uint128).max`. `withdraw` then treats that as a legitimate balance and allows transfers up to that inflated value (subject to contract token holdings).
- **Impact:** Even aside from a single drain via `emergencyWithdraw`, an attacker can alternate or follow with `withdraw` to pull additional tokens until the contract is empty. This is a second drain path from the same root cause (missing balance validation in `_processWithdrawal`).

---

## `uint128` balance overflow on deposit (availability / insolvency)

- **Location:** `StablecoinDEX.sol` : `deposit`
- **Mechanism:** `balances[msg.sender][token] += amount` uses `uint128` storage. Deposits that would push a user’s balance above `type(uint128).max` revert in 0.8.x checked arithmetic.
- **Impact:** Not direct theft, but a large depositor (or aggregated deposits) can be permanently unable to credit funds—a griefing/DoS on large accounts. If combined with other accounting bugs, mismatches between `totalDeposits` and real balances could worsen insolvency scenarios.

---

## Notes on non-findings (intentionally omitted)

- **`MAX_PRICE_DEVIATION` unused:** Design gap, not an exploitable path by itself; makers set their own limit prices.
- **`MockTIP20` minter centralization:** Expected for a mock token.
- **Partial-fill dust / linked-list ordering:** Operational/UX issues, not fund-loss vulnerabilities.
- **`UserBalance.locked` unused:** Dead design; locking is implemented by deducting `balances` at `placeOrder`, and that internal accounting is internally consistent for fills/cancels.

---

## Summary

| Severity | Finding |
|----------|---------|
| **Critical** | `emergencyWithdraw` / `_processWithdrawal` — full contract drain |
| **High** | `withdraw` reentrancy with hook-bearing tokens |
| **High** | Fee-on-transfer token over-credit → insolvency / theft |
| **Medium** | Unauthorized `cancel` — griefing / liquidity DoS |
| **Low** | `uint128` deposit overflow — large-account DoS |

The most urgent fix is removing or hardening `emergencyWithdraw` (balance check + access control, or delete the function), then applying CEI on `withdraw` and adding `msg.sender == order.maker` on `cancel`. I can outline concrete patches in Agent mode if you want them implemented.

