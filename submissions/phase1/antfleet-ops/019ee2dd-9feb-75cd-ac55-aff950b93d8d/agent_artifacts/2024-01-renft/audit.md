# Audit: 2024-01-renft

## Factory Policy Is Never Activated in Deployment Scripts
- Location: `scripts/base/BaseDeploy.sol` : `_setUpPolicy` (used by `DeployProtocol.run`) and `src/policies/Factory.sol` : `deployRentalSafe`
- Mechanism: `DeployProtocol` deploys the `Factory` policy but never calls `_setUpPolicy(address(factory))`, so the Kernel never grants the `STORE.addRentalSafe` permission to the Factory. `Factory.deployRentalSafe` then calls `STORE.addRentalSafe`, which is protected by the module’s `permissioned` modifier and Kernel’s `modulePermissions` check.
- Impact: All rental-safe deployments revert; the protocol cannot create rental wallets.

## Guard Checks Wrong Address for `disableModule` Whitelist
- Location: `src/policies/Guard.sol` : `_checkTransaction` and `src/libraries/RentalConstants.sol` : `gnosis_safe_disable_module_offset`
- Mechanism: `Safe.disableModule(address prevModule, address module)` has the module to remove as its second argument, located at calldata offset `0x44`, but the guard reads the value at offset `0x24` (`gnosis_safe_disable_module_offset`). Therefore the whitelist check is applied to `prevModule` instead of the module actually being disabled.
- Impact: An attacker can disable a non-whitelisted Safe module (e.g., the Stop policy) by ensuring the preceding module in the Safe module list is a whitelisted extension, or conversely have legitimate disables blocked, bypassing the intended module-safety controls.

## Order Metadata EIP-712 Hash Omits `orderType` and `emittedExtraData`
- Location: `src/packages/Signer.sol` : `_deriveOrderMetadataHash`
- Mechanism: The type string for `OrderMetadata` includes `orderType` and `emittedExtraData`, but the actual `abi.encode` only hashes `rentDuration` and the hooks. Because the server-side signature and the zone-hash check both depend on this hash, neither field is cryptographically bound.
- Impact: A fulfiller can change the `orderType` of a signed rental (altering whether it is processed as BASE/PAY/PAYEE and how it is later settled) and can inject arbitrary `emittedExtraData` into protocol events while still passing all signature and metadata validations.

## Rental Order Hash Missing `rentalWallet` Causes Storage Collisions
- Location: `src/packages/Signer.sol` : `_deriveRentalOrderHash` and `src/modules/Storage.sol` : `addRentals`
- Mechanism: The `RentalOrder` type string contains `address rentalWallet`, but the encoded data fed to `keccak256` in `_deriveRentalOrderHash` omits it. The resulting order hash stored by `Storage.addRentals` and removed by `Storage.removeRentals` is therefore identical for rental orders that are otherwise the same but delivered to different protocol safes.
- Impact: Distinct rentals can share one stored order hash; stopping one can delete/alter state needed for another, leaving assets stuck or incorrectly unprotected by the guard.

## CREATE2 Salt Generator Discards the Extra Entropy
- Location: `src/Create2Deployer.sol` : `generateSaltWithSender`
- Mechanism: The function shifts the `bytes12 data` argument right by `0xA0` (160 bits), which zeroes it before OR-ing it into the salt. Only the deployer address is embedded; the intended protocol-version entropy is never included.
- Impact: Different protocol versions lose their unique salts, so identical init code deployed under a new version reuses the same salt and fails because `Create2Deployer.deploy` marks the address as already deployed, breaking versioned redeployments and the intended salt-uniqueness guarantee.

## Reentrancy via Hooks During Rental Stop
- Location: `src/policies/Stop.sol` : `_removeHooks` (called from `stopRent` and `stopRentBatch`)
- Mechanism: `stopRent`/`stopRentBatch` call external `IHook(target).onStop` before settling escrow payments and before `Storage.removeRentals` removes the active order; there is no reentrancy guard, so the order and rental records are still live during the hook call.
- Impact: A malicious whitelisted hook (or a callback-bearing token reached during reclaim) can reenter `stopRent` while the original call still treats the order as active, allowing double settlement attempts, inconsistent escrow accounting, or denial-of-service by forcing reverts.
