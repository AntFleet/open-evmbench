# Audit: 2024-01-renft

## Guard Bypass via Active Hook
- Location: `src/policies/Guard.sol` : `checkTransaction`
- Mechanism: In the `checkTransaction` function, the guard fetches the configured hook for the target address. If a hook exists and is active (`hook != address(0) && isActive`), the guard forwards the transaction validation entirely to the hook via `_forwardToHook` and explicitly skips the basic transaction checks (`_checkTransaction`). This makes the core protection logic—which prevents the transfer, approval, or batch transfer of actively rented ERC721/ERC1155 assets—mutually exclusive with the hook middleware.
- Impact: If the `GUARD_ADMIN` configures a hook for a token contract that does not strictly implement its own rental transfer validations (e.g., a simple tracking, analytics, or reward hook like `ERC1155RewardHook`), the basic guard protections are bypassed. A malicious renter could then freely call `safeTransferFrom` or `approve` on the rented NFTs, transferring the rented assets out of the Safe and effectively stealing them. The guard should always enforce basic rental invariants before or alongside forwarding to a hook.
