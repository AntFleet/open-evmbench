# Audit: 2023-12-ethereumcreditguild

## Findings

### 1. ProfitManager.notifyPnL does not verify that profit has been transferred
- **Location:** `src/governance/ProfitManager.sol` : `notifyPnL`
- **Mechanism:** The function is callable by any address with the `GAUGE_PNL_NOTIFIER` role (typically a lending term). For a profit (`amount > 0`), it immediately distributes the reported amount: it increases the surplus buffer, transfers to `otherRecipient`, calls `distribute()` (which burns CREDIT from the ProfitManager), and updates gauge profit indices. None of these steps check that the ProfitManager’s actual CREDIT balance has increased by `amount`. The caller is assumed to have transferred the tokens beforehand, but the function does not enforce this.
- **Impact:** A malicious contract holding the `GAUGE_PNL_NOTIFIER` role can call `notifyPnL` with a fabricated profit. The ProfitManager will distribute CREDIT from its own balance (including the surplus buffer) to the designated recipients, effectively draining the surplus buffer and any other CREDIT held by the contract. This can lead to a complete loss of the first-loss capital and destabilise the protocol.

### 2. LendingTermOffboarding is granted the GOVERNOR role
- **Location:** `src/governance/LendingTermOffboarding.sol` : `offboard`, `cleanup`
- **Mechanism:** The `offboard` function calls `SimplePSM(psm).setRedemptionsPaused(true)`, and `cleanup` calls `core().revokeRole(...)` and `SimplePSM(psm).setRedemptionsPaused(false)`. All of these functions require the `GOVERNOR` role. Consequently, the `LendingTermOffboarding` contract must be granted the `GOVERNOR` role, which gives it unrestricted control over the entire protocol (e.g., minting tokens, changing Core, etc.). The contract’s external functions are mostly permissionless (only guarded by `whenNotPaused`), so any flaw in the offboarding logic or a governance attack that manipulates `canOffboard` could allow an attacker to wield the full power of the GOVERNOR role.
- **Impact:** If the contract is compromised or if a governance manipulation succeeds, an attacker can steal all funds, alter any protocol parameter, or brick the system. The excessive privilege assigned to this contract is a severe security risk.

### 3. AuctionHouse.bid can lead to reentrancy in LendingTerm.onBid via malicious collateral
- **Location:** `src/loan/AuctionHouse.sol` : `bid` → `LendingTerm.onBid`
- **Mechanism:** The `bid` function calls `LendingTerm.onBid`, which performs `safeTransfer` of the collateral token to the borrower and/or bidder. If the collateral token is an ERC‑777 or otherwise implements a callback on transfer, the recipient can re‑enter `AuctionHouse.bid` or other functions. The auction state is updated before the call (`endTime` set, `nAuctionsInProgress` decreased), and `onBid` checks that the loan is not already closed, but the interplay of multiple state changes and external calls could still be exploited in edge cases.
- **Impact:** A carefully crafted collateral token and a malicious recipient could potentially re‑enter to manipulate auction outcomes, steal funds, or cause a denial of service. The likelihood is reduced by the checks in place, but the pattern is a known risk.

### 4. Division by zero in ProfitManager.notifyPnL when creditTotalSupply is zero
- **Location:** `src/governance/ProfitManager.sol` : `notifyPnL` (loss handling)
- **Mechanism:** In the loss case, after depleting the surplus buffer, the remaining loss is socialised by updating the credit multiplier:
  ```solidity
  uint256 newCreditMultiplier = (creditMultiplier * (creditTotalSupply - loss)) / creditTotalSupply;
  ```
  If `creditTotalSupply` is zero (e.g., all loans have been closed and no CREDIT exists), this expression divides by zero and reverts. While an extreme edge case, it could be triggered by a misbehaving lending term that calls `notifyPnL` with a loss when no CREDIT is outstanding.
- **Impact:** The loss reporting mechanism would revert, potentially blocking the protocol from handling bad debt and freezing related operations.
