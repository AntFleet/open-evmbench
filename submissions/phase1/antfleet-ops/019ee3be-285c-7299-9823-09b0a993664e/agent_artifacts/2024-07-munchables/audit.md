# Audit: 2024-07-munchables

## Stuck ETH Due to Missing Value Validation
- Location: src/distributors/FundTreasuryDistributor.sol : receiveTokens
- Mechanism: The payable function loops over TokenBags and only performs `if (msg.value != amount) revert` inside the `tokenContract == address(0)` branch for each individual bag; there is no summation of all ETH bags or comparison of total `msg.value` against the sum of ETH amounts before or after the loop, and excess ETH has no refund path or recovery mechanism.
- Impact: An attacker (or misbehaving RewardsManager) can send ETH with a non-ETH bag or extra value, permanently locking the ETH inside the distributor with no way for the owner or any role to withdraw it.

## Unauthorized Role Lookup via msg.sender in Cross-Contract Calls
- Location: src/config/ConfigStorage.sol : getRole / getContractRole (called from BaseConfigStorage modifiers)
- Mechanism: `getRole(Role)` unconditionally does `getContractRole(_role, msg.sender)` using the immediate caller as the `_contract` key in `roleStorage[keccak256(abi.encode(_role, _contract))]`, and modifiers such as `onlyRole` / `onlyOneOfRoles` / `onlyUniversalRole` rely on this without any whitelist or context check on who the caller is.
- Impact: Any contract that is granted a role for itself can impersonate another contract's role by making an internal call that sets `msg.sender` to the victim contract address, or an attacker can cause a role check to succeed/fail unexpectedly when the same EOA is used from different calling contracts.

## Reentrancy via External Call in ETH Distribution Path
- Location: src/distributors/FundTreasuryDistributor.sol : receiveTokens (ETH branch)
- Mechanism: After the `onlyConfiguredContract` check, the function performs an unbounded `payable(_treasury).call{value: amount}("")` with no reentrancy guard and before any state updates that would prevent re-entry; the same function is also the only entry point that can be called by the RewardsManager.
- Impact: If the configured Treasury contract is malicious or compromised, it can re-enter `receiveTokens` (or any other function on the distributor) during the ETH transfer, allowing arbitrary re-execution of distribution logic or state manipulation on subsequent calls once additional state variables are added.

## Arbitrary Schnibble Injection via Reward Spray
- Location: src/managers/AccountManager.sol : rewardSpray / removeSpray
- Mechanism: Both functions are gated only by `onlyRole(Role.NFTOracle)` and directly mutate `players[_player].unfedSchnibbles` or the `unclaimedSchnibbles` mapping with any `_schnibbles` value supplied by the caller; there is no cap, no relation to any on-chain lock/weight, and no event that cannot be forged by the same role.
- Impact: The NFTOracle role holder can grant or remove arbitrary quantities of schnibbles to any address (registered or not), bypassing all lock-weighted, pet, referral, and harvest calculations and enabling unbounded inflation of player resources.

## Incorrect Storage Key Used for LandManager Address
- Location: src/managers/AccountManager.sol : _reconfigure (and LandManager references)
- Mechanism: `landManager` is initialized with `configStorage.getAddress(StorageKey.PrimordialsEnabled)` instead of a dedicated `StorageKey` for the LandManager contract; all subsequent calls (`forceHarvest` path, `updatePlotMetadata`) therefore resolve to whatever address (or zero) is stored under that unrelated key.
- Impact: The AccountManager will make calls to an unintended contract (or address(0)), causing `forceHarvest` and related land accounting to either revert, do nothing, or execute attacker-controlled code if that storage slot is later overwritten.
