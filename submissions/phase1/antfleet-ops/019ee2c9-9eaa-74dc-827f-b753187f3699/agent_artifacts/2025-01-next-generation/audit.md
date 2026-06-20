# Audit: 2025-01-next-generation

## Arbitrary EIP-712 domain replay in the trusted forwarder
- Location: [Forwarder.sol](/Users/augstar/open-evmbench/audit_sources/2025-01-next-generation/contracts/Forwarder.sol:93) : `execute`
- Mechanism: `execute()` and `verify()` accept `domainSeparator` as a caller-supplied argument and pass it into `_verifySig()` without checking that it is this forwarder’s own domain separator ([Forwarder.sol](/Users/augstar/open-evmbench/audit_sources/2025-01-next-generation/contracts/Forwarder.sol:144)). As a result, signatures are not bound to the deployed trusted forwarder, nor to its chain/domain. Any signature over the same `ForwardRequest` fields can be replayed here by supplying the separator of the domain the victim originally signed for. A concrete exploit is signing a request for an untrusted or different forwarder, then submitting that same signed payload to the token’s trusted forwarder with the foreign domain separator; the trusted forwarder will still recover `req.from` and execute the transfer.
- Impact: An attacker can turn signatures intended for another forwarder/domain into valid transfers through the trusted forwarder, causing unauthorized token transfers and charging the victim the gasless base fee.

## `transferFrom` can charge more than the approved allowance
- Location: [Token.sol](/Users/augstar/open-evmbench/audit_sources/2025-01-next-generation/contracts/Token.sol:166) : `transferFrom`
- Mechanism: `transferFrom()` calls `transferSanity(sender, recipient, amount)` before `super.transferFrom(...)` ([Token.sol](/Users/augstar/open-evmbench/audit_sources/2025-01-next-generation/contracts/Token.sol:156)), and `transferSanity()` calls `_payTxFee(sender, amount)` when fees are enabled. `_payTxFee()` immediately debits the owner’s balance via `_update(from, _feesFaucet, txFees)` ([Token.sol](/Users/augstar/open-evmbench/audit_sources/2025-01-next-generation/contracts/Token.sol:126)), but the later allowance spend only accounts for `amount`, not `amount + txFees`. So a spender approved for `N` tokens can force the owner to lose `N + fee(N)` tokens in one call.
- Impact: Any approved spender can drain more tokens than the owner authorized. With a 10% fee, a `100` token allowance lets the spender extract `110` tokens from the owner; with the max fee rate, the loss can reach `2x` the approved amount.

## Blacklisted/paused accounts can still create spend permissions
- Location: [ERC20MetaTxUpgradeable.sol](/Users/augstar/open-evmbench/audit_sources/2025-01-next-generation/contracts/ERC20MetaTxUpgradeable.sol:48) : `permit`
- Mechanism: Transfer paths enforce `adminSanity()`, but approval paths do not. `permit()` directly calls `_approve(owner, spender, value)` after signature recovery, with no paused or blacklist checks. The token also does not override OZ `approve()`, so on-chain approvals likewise bypass the blacklist/pause policy entirely. That means a frozen account can still create or refresh allowances while it is supposed to be immobilized.
- Impact: A blacklisted or emergency-paused account can pre-authorize spenders during the freeze. Once the account is unblacklisted or the system is unpaused, those standing allowances can be used immediately to pull funds without any new action from the holder.

