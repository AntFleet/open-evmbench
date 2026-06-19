# Audit: 2025-01-next-generation

## Missing Access Control in setOwner
- Location: `Token.sol` : `setOwner`
- Mechanism: The `setOwner` function lacks any access control modifier (such as `onlyRole(OWNER)` or `onlyOwner`). It allows any arbitrary address to call the function and assign themselves (or any other address) as the new owner by granting the `OWNER` (`DEFAULT_ADMIN_ROLE`) role and revoking it from the current owner.
- Impact: An attacker can take full ownership of the `EURFToken` contract. This grants them `DEFAULT_ADMIN_ROLE`, which allows them to upgrade the contract implementation to a malicious version (via `_authorizeUpgrade`), assign themselves administrative/minting roles, and completely compromise the token and its users' funds.

## Missing Access Control in Controller and Minter Management Functions
- Location: `ERC20ControlerMinterUpgradeable.sol` : `addController`, `removeController`, `setMasterMinter`, `addMinter`, `removeMinter`
- Mechanism: These critical administrative functions are defined with `external` visibility but completely lack access control modifiers (e.g., `onlyRole(DEFAULT_ADMIN_ROLE)` or `onlyRole(MASTER_MINTER)`). Any external account can invoke these functions to grant or revoke the `CONTROLLER`, `MASTER_MINTER`, and `MINTER_ROLE` roles, as well as set minter allowances.
- Impact: An attacker can add themselves as a `MINTER_ROLE` with an unlimited allowance and mint an infinite supply of tokens, destroying the token's economy. They can also add themselves as `MASTER_MINTER` to control all minting operations, or as a `CONTROLLER` to trigger the `safetySwitch` and halt contract operations.
