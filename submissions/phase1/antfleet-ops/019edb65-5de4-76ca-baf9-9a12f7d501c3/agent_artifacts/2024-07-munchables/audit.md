# Audit: 2024-07-munchables

# Findings

## 1. Unauthorized yield/gas claiming in RewardsManager
- **Location:** `src/managers/RewardsManager.sol` : `claimYieldForContracts`, `claimGasFeeForContracts`
- **Mechanism:** Both functions are declared `external` without any access modifier (`onlyRole`, `onlyAdmin`, etc.). The `RewardsManager` contract is configured as the Blast governor for many other contracts, giving it the right to claim their yield and gas fees. An attacker can call these functions directly, passing arbitrary contract addresses, and force the claiming of yield/gas from any contract that has granted this `RewardsManager` authority. The claimed funds are then forwarded to the treasury via the distributors, so the attacker cannot steal them directly, but the action is completely permissionless and bypasses the intended role‑based access control.
- **Impact:** An attacker can trigger premature or unscheduled claiming of yield and gas fees, potentially disrupting the protocol’s claim schedule, front‑running legitimate claims, or causing the treasury to receive funds at undesirable times. Although the funds themselves are not stolen, the missing access control represents a privilege escalation that undermines the security model.

## 2. Broken ERC20 rescue in MigrationManager
- **Location:** `src/managers/MigrationManager.sol` : `rescue`
- **Mechanism:** The `rescue` function is intended to allow the admin to recover stuck tokens. For ERC20 tokens, it calls `IERC20(_tokenContract).transferFrom(address(this), _returnAddress, _quantity)`. This function requires the caller (`address(this)`) to have an allowance from the token holder (`address(this)`) to move the tokens, which is never set. The correct call should be `transfer`. Consequently, any attempt to rescue ERC20 tokens will revert, permanently locking them in the contract.
- **Impact:** The admin cannot recover ERC20 tokens that are accidentally sent to the `MigrationManager` contract. While this does not allow an attacker to steal funds, it makes the designated rescue mechanism unusable, potentially locking legitimate tokens forever.
