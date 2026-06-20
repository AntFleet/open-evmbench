# Audit: 2024-05-munchables

## Missing Return Value Checks on ERC20 Transfers
- Location: src/distributors/FundTreasuryDistributor.sol : receiveTokens; src/managers/LockManager.sol : unlock (and _lock path)
- Mechanism: `receiveTokens` performs `IERC20(tokenContract).transferFrom(...)` (and `payable(_treasury).transfer` for ETH) without checking the `bool` return value before emitting `DistributedTokens` and returning. Similarly, `unlock` (and the internal transfer path in `_lock`) calls `token.transfer(...)` or `token.transferFrom(...)` with no return-value check or `SafeERC20` wrapper before mutating `lockedToken.quantity`.
- Impact: An attacker (or a misbehaving/malicious ERC20) can cause the state change (tokens marked distributed or unlocked) while the actual token movement fails or returns false, resulting in permanent loss of tokens for the protocol or users who believe they have received/unlocked funds.

## Excess Migration Funds Left in Contract with No Withdrawal Path
- Location: src/managers/MigrationManager.sol : lockFundsForAllMigration + _migrateNFTs
- Mechanism: `lockFundsForAllMigration` accepts the full pre-discount amount from the user; `_migrateNFTs` then only forwards `(totalLockAmount * discountFactor) / 10e12` into `LockManager.lockOnBehalf`. The difference (the "excess") remains permanently in the `MigrationManager` balance with no `withdraw`, `sweep`, or admin-only rescue function.
- Impact: An attacker who triggers migration (or the deployer) can force arbitrary amounts of ETH/USDB/WETH to be trapped in the contract forever, creating a direct loss-of-funds vector and a griefing opportunity against users who over-send.

## Duplicate Addresses Allowed in Notifiable List
- Location: src/config/ConfigStorage.sol : addNotifiableAddress + addNotifiableAddresses + notify
- Mechanism: The `notifiableAddresses` array is appended to without any `contains` check; `notify` (and `manualNotify`) iterates the entire array and calls `configUpdated()` on every entry, including duplicates.
- Impact: An attacker with `onlyOwner` access (or a compromised owner) can add the same address many times; every subsequent `set*` call with `_notify=true` will then make multiple external calls to the same contract, enabling denial-of-service via gas exhaustion or reentrancy amplification on any notifiable contract.

## Unchecked Array Length in Manual Notify
- Location: src/config/ConfigStorage.sol : manualNotify
- Mechanism: `manualNotify(uint8 _index, uint8 _length)` loops `i = _index; i < _index + _length` and calls `configUpdated()` on `notifiableAddresses[i]` with only a bounds check against `notifiableAddresses.length`; it does not validate that `_index + _length` fits in a `uint256` or that the caller cannot supply `_length` values that cause an out-of-bounds read before the `break`.
- Impact: A malicious owner can supply crafted `_index`/`_length` values that either skip intended addresses or, combined with a very large `notifiableAddresses` array, cause the loop to perform unexpected external calls, potentially bypassing intended notification ordering or enabling griefing.

## No Check That Treasury Remains Non-Zero After Reconfigure
- Location: src/distributors/FundTreasuryDistributor.sol : _reconfigure + receiveTokens
- Mechanism: `_reconfigure` only sets `_treasury` if `getAddress(StorageKey.Treasury) != address(0)`; subsequent `receiveTokens` calls will revert with `InvalidTreasuryError` only if `_treasury` is still zero at call time, but nothing prevents the config owner from setting the treasury key back to zero between calls.
- Impact: An attacker who can call `setAddress` (owner) can temporarily zero the treasury key, causing all subsequent reward distributions to revert while the RewardsManager still believes the distributor is functional, leading to stuck yield.

## Sub-Account Removal Does Not Clean Up All References
- Location: src/managers/AccountManager.sol : _removeSubAccount
- Mechanism: When removing a sub-account the code deletes `mainAccounts[_subAccount]` and removes it from the main account's list, but never clears any pending `sprayProposals`, `unclaimedSchnibbles`, or `lockedTokens` entries that may still reference the now-orphaned sub-account address.
- Impact: An attacker who repeatedly adds/removes sub-accounts can leave stale proposal or lock data that later `execSprayProposal` or `getLocked` calls will still act upon, allowing unauthorized distribution of schnibbles or locked tokens to addresses that are no longer valid sub-accounts.
