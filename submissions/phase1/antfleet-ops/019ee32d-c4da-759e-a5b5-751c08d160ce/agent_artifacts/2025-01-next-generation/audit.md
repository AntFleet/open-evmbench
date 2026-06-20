# Audit: 2025-01-next-generation

## Signature Bypass via address(0) in transferWithAuthorization Allows Arbitrary Token Minting
- Location: `contracts/ERC20MetaTxUpgradeable.sol` : `transferWithAuthorization`
- Mechanism: The contract verifies the off-chain authorization signature by calling `ECDSA.recover`. If the signature provided is invalid (e.g., empty or malformed `v, r, s` inputs), `ECDSA.recover` returns `address(0)`. When the `holder` parameter is explicitly passed as `address(0)`, the safety check `signer != holder` evaluates to `address(0) != address(0)`, thereby bypassing the signature validation. Since `transferSanity` does not prevent `holder` from being `address(0)` (which is true by default when `_txfeeRate` is 0), the execution path triggers `_update(address(0), spender, value)`. In OpenZeppelin ERC20 v5, executing `_update` with a source of `address(0)` is interpreted as a token minting operation, successfully creating `value` new tokens for the receiver.
- Impact: Any user can bypass signature validation to mint an infinite amount of EURF tokens to any arbitrary address.

## Forwarder Signature Bypass via address(0) Allows Arbitrary Calling and Token Minting
- Location: `contracts/Forwarder.sol` : `execute`
- Mechanism: The `execute` function relies on `_verifySig` to validate meta-transactions. If a transaction request sets `req.from` to `address(0)` and contains an invalid signature, `digest.recover(sig)` yields `address(0)`. Because both the recovered signer and `req.from` match `address(0)`, the signature restriction is bypassed. The Forwarder subsequently executes an external call to the `EURFToken` contract on behalf of `address(0)`. When the token contract process runs `transfer(recipient, amount)`, `_msgSender()` evaluates to `address(0)` (appended via ERC-2771 calldata from the Forwarder). This translates directly to an internal call of `_update(address(0), recipient, amount)`, which triggers a mint.
- Impact: Anyone can abuse the `Forwarder` using `address(0)` with a dummy signature to call the `transfer` function on the token contract, resulting in unconstrained minting of tokens.

## Administrator Role Tracking Breakage via Enumerable Set Swapping in setAdministrator
- Location: `contracts/ERC20AdminUpgradeable.sol` : `setAdministrator`
- Mechanism: The function `setAdministrator(address newAdmin)` manages the `ADMIN` role by reading the current administrator via `getRoleMember(ADMIN, 0)`, revoking it, and granting the new address the `ADMIN` role. However, if multiple administrators are granted roles through standard AccessControl mechanisms, the underlying `EnumerableSet` grows. When `revokeRole` is called on an active administrator, the `EnumerableSet` library shifts the last element of the set into the removed item's index (index 0) to maintain compactness. Consecutive administrative updates will pull and revoke the incorrect administrator dynamically placed at index 0.
- Impact: Active administrators can be unexpectedly revoked, whereas old or unauthorized administrators are left with full administrative control, violating intended access controls.

## Redundant Fee Logic Locking Transfers when Fee Faucet is Unset
- Location: `contracts/Token.sol` : `_payTxFee`
- Mechanism: In `_payTxFee`, the contract enforces that the sender's balance is sufficient to cover both the transaction amount and the computed fee amount via `if (balanceOf(from) < txFees + txAmount) revert BalanceTooLow(...)`. However, if `_txfeeRate` is greater than 0 but no `_feesFaucet` address has been set (`_feesFaucet == address(0)`), no transaction fee is actually collected or transferred. Nonetheless, the contract still checks for and enforces the balance limit.
- Impact: Senders who have enough balance to complete their actual transfers (but not the additional uncollected fee amount) will find their transfer transactions unexpectedly reverting even though no transaction fee is deducted.
