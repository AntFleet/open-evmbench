# Audit: 2025-01-next-generation

## Forwarder Signatures Are Replayable Across Domains/Chains
- Location: `Forwarder.sol` : `_verifySig`, `execute`
- Mechanism: `_verifySig` accepts `domainSeparator` as caller-supplied input instead of computing and enforcing the forwarder’s own EIP-712 domain, and `ForwardRequest` has no deadline. A valid signature over the same request can therefore be replayed wherever the request fields and nonce line up, including another chain/deployment using the same token/forwarder addresses.
- Impact: An attacker can reuse a user’s signed forward request on another compatible deployment or at an arbitrary later time to execute an unintended token transfer and collect the gasless base fee.

## `forceTransfer` Can Mint Or Burn Through The Zero Address
- Location: `ERC20AdminUpgradeable.sol` : `forceTransfer`
- Mechanism: `forceTransfer` calls OpenZeppelin ERC20 v5’s internal `_update(from, to, amount)` directly. `_update(address(0), to, amount)` mints and `_update(from, address(0), amount)` burns, but `adminSanity` never rejects `from == address(0)` or `to == address(0)`.
- Impact: Any `ADMIN` can bypass the minter allowance system and `_operating` switch by minting unlimited tokens with `forceTransfer(address(0), to, amount)`, or burn arbitrary user balances with `forceTransfer(victim, address(0), amount)`.

## Removed Controller Can Re-Enable Operations
- Location: `ERC20ControlerMinterUpgradeable.sol` : `safetySwitch`
- Mechanism: When a controller disables operations, `_operatingController` stores its address. The re-enable branch allows `_operatingController` to turn operations back on without checking whether it still has `CONTROLLER`. If the controller is removed after disabling operations, the stale stored address remains authorized.
- Impact: A compromised or removed controller can re-enable minting and burning after governance/admin attempted to revoke its authority during an incident.

## Transfer Fees Bypass Allowance And Signed Value
- Location: `Token.sol` : `transferFrom`, `transferWithAuthorization`, `_payTxFee`
- Mechanism: `transferSanity` calls `_payTxFee(sender, amount)` before `super.transferFrom` or signature execution. `_payTxFee` moves `txFees` directly from the token owner with `_update`, while allowance/signature accounting only covers `amount`, not `amount + txFees`.
- Impact: An approved spender can cause a holder to lose more than the approved allowance, with the excess routed to `_feesFaucet`. Likewise, a `transferWithAuthorization` signer authorizes `value` but can be debited `value + txFees`.

## Gasless Base Fee Is Not Authorized By The User Signature
- Location: `Forwarder.sol` : `execute`; `Token.sol` : `payGaslessBasefee`
- Mechanism: The signed `ForwardRequest` authorizes only the forwarded token `transfer` calldata. It does not bind the gasless fee amount or the paymaster. After executing the transfer, `execute` unconditionally calls `payGaslessBasefee(req.from, _msgSender())`, using the token contract’s current `_gaslessBasefee`.
- Impact: Any party with a valid signed forward request can execute it and extract the current gasless base fee from the signer, even if that fee amount or payee was not part of what the signer authorized. A mempool observer can also front-run the intended relayer and steal the fee reward.

## Gasless Base Fee Bypasses Recipient Blacklist
- Location: `Token.sol` : `payGaslessBasefee`
- Mechanism: `payGaslessBasefee` only checks that `msg.sender` is the trusted forwarder, then transfers `_gaslessBasefee` with `_update(payer, paymaster, _gaslessBasefee)`. It does not call `adminSanity`, so it does not reject a blacklisted `paymaster`.
- Impact: A blacklisted address can still receive EURF by relaying valid forwarder transactions and collecting the gasless base fee, bypassing the blacklist’s recipient restriction.

