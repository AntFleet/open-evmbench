# Audit: 2024-03-coinbase

## Paymaster refunds more ETH than it actually recovers
- Location: `audit_sources/2024-03-coinbase/src/MagicSpend/MagicSpend.sol` : `validatePaymasterUserOp`, `postOp` (`109-139`, `143-162`)
- Mechanism: In the paymaster flow, the contract withholds `maxCost` by crediting only `withdrawAmount - maxCost` to `_withdrawableETH`, then later refunds `maxGasCost - actualGasCost` in `postOp`. That means the user is charged only `actualGasCost`. But EntryPoint charges the paymaster more than that: it calls `postOp` with `actualGasCost` before `postOp` gas is counted, then adds the gas spent inside `postOp` itself before final settlement (`lib/account-abstraction/contracts/core/EntryPoint.sol:556-590`). MagicSpend therefore refunds based on an incomplete cost figure and systematically under-recovers what the paymaster deposit actually lost.
- Impact: Any user with a valid signed withdrawal can extract slightly more ETH than intended on every gas-sponsored withdrawal, gradually draining sponsor funds through repeated use.

## The same ETH can be reserved by multiple withdrawals in one bundle
- Location: `audit_sources/2024-03-coinbase/src/MagicSpend/MagicSpend.sol` : `validatePaymasterUserOp` (`130-139`)
- Mechanism: `validatePaymasterUserOp` only checks `address(this).balance >= withdrawAmount` for the current operation, but it never subtracts already-reserved amounts from an aggregate available-balance tracker. EntryPoint validates every operation in a bundle before executing any of them (`lib/account-abstraction/contracts/core/EntryPoint.sol:92-109`), so multiple sponsored withdrawals can all pass validation against the same ETH balance. When execution/post-op settlement begins, later operations can hit insufficient local ETH and revert during payout.
- Impact: An attacker with valid signed requests can over-subscribe the paymaster in a single batch and cause bundled sponsored withdrawals to fail, griefing bundlers and denying service to legitimate withdrawals that share the batch.

## `expiry == 0` is “expired” for `withdraw()` but “never expires” for paymaster use
- Location: `audit_sources/2024-03-coinbase/src/MagicSpend/MagicSpend.sol` : `validatePaymasterUserOp`, `withdraw` (`127-128`, `181-190`)
- Mechanism: The direct withdrawal path treats `expiry` literally and reverts once `block.timestamp > expiry`, so `expiry == 0` is immediately expired. The paymaster path does not do that check; it just packs `withdrawRequest.expiry` into ERC-4337 `validationData`. EntryPoint then interprets `validUntil == 0` as `type(uint48).max` (`lib/account-abstraction/contracts/core/Helpers.sol:23-30`). So the same signed request is expired in `withdraw()` but valid forever in `validatePaymasterUserOp`.
- Impact: A signed withdrawal request with zero expiry can still be used indefinitely through the paymaster path, bypassing the intended expiration boundary.

I did not find another concrete exploit path in `CoinbaseSmartWallet`, `MultiOwnable`, `ERC1271`, `WebAuthn`, or the factory beyond these issues.

