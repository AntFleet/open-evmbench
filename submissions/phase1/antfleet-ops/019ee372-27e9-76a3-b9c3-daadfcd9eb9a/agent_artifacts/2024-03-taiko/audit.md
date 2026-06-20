# Audit: 2024-03-taiko

## Unhandled Reverts in `ERC20Vault._handleMessage` for Non-Standard ERC20 Tokens

- Location: `packages/protocol/contracts/tokenvault/ERC20Vault.sol` : `_handleMessage`
- Mechanism: When bridging a token that is native to the current chain (i.e. acting as the canonical token), `ERC20Vault` directly calls `meta.decimals()`, `meta.symbol()`, and `meta.name()` without any `try/catch` wrappers. If the ERC20 token does not implement these optional metadata functions or returns non-standard types (e.g., `bytes32` instead of `string`, like the Maker (MKR) token), the calls will revert. 
- Impact: Users cannot bridge standard-but-metadata-lacking ERC20 tokens or tokens with non-standard return types for metadata properties. This bricks the standard bridging flow for these assets.
