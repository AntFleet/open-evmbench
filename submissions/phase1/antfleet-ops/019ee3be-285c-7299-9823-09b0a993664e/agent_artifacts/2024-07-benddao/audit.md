# Audit: 2024-07-benddao

## Missing Access Control on Role Management Functions
- Location: src/ACLManager.sol : addPoolAdmin, removePoolAdmin, addEmergencyAdmin, removeEmergencyAdmin, addOracleAdmin, removeOracleAdmin
- Mechanism: These functions directly invoke `grantRole`/`revokeRole` (inherited from AccessControlUpgradeable) with no additional modifiers such as `onlyRole(DEFAULT_ADMIN_ROLE)`. While OpenZeppelin's `grantRole` implementation internally enforces `onlyRole(getRoleAdmin(role))`, the missing explicit guards on the IACLManager interface methods (combined with public visibility and no custom checks in initialize or elsewhere) allows any caller that somehow obtains the admin role (e.g., via misconfiguration, upgrade, or initial setup race) to arbitrarily manage POOL_ADMIN_ROLE, EMERGENCY_ADMIN_ROLE, and ORACLE_ADMIN_ROLE without protocol-level authorization.
- Impact: An attacker that gains (or is granted) DEFAULT_ADMIN_ROLE can add/remove arbitrary addresses as pool/emergency/oracle admins, bypassing intended governance and enabling unauthorized actions such as pausing pools, liquidations, or oracle price updates.

## Incorrect Event Emission in Setter
- Location: src/AddressProvider.sol : setDelegateRegistryV2
- Mechanism: The function correctly updates `_addresses[DELEGATE_REGISTRY_V2]` and emits an event, but unconditionally emits `YieldRegistryUpdated` (with the wrong event signature and parameters) instead of a DelegateRegistryV2-specific event.
- Impact: Off-chain indexers/monitors receive misleading events; an attacker monitoring for registry changes could miss updates to the delegate registry, enabling undetected delegation abuse in yield/ERC721 flows.

## Potential Division-by-Zero in Price Conversion Path
- Location: src/PriceOracle.sol : getAssetPriceFromBendNFTOracle
- Mechanism: When `NFT_BASE_CURRENCY != BASE_CURRENCY`, the conversion performs `(nftPriceInNftBase * nftBaseCurrencyPriceInBase) / NFT_BASE_CURRENCY_UNIT` with no guard that `NFT_BASE_CURRENCY_UNIT` (set in initialize) is non-zero; the same unit is used in other paths without validation.
- Impact: If an admin (via oracle admin role) initializes or leaves `NFT_BASE_CURRENCY_UNIT=0`, any price query for an NFT asset using the BendNFTOracle fallback path reverts (or produces undefined behavior), allowing denial-of-service on liquidations, borrows, and health factor checks that rely on `getAssetPrice`.
