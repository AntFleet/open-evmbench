# Audit: 2024-03-coinbase

## Cross-chain replay of privileged wallet actions
- Location: `src/SmartWallet/CoinbaseSmartWallet.sol` : `validateUserOp`, `executeWithoutChainIdValidation`, `canSkipChainIdValidation`
- Mechanism: For `executeWithoutChainIdValidation`, the wallet replaces the normal EntryPoint hash with `getUserOpHashWithoutChainId`, deliberately omitting `block.chainid`. The allowlist includes owner mutations and `UUPSUpgradeable.upgradeToAndCall`, so one valid signature over these privileged self-calls is valid on every chain where the same wallet address exists.
- Impact: Anyone who sees a signed replayable operation can submit it on other chains. This can remove/add owners unexpectedly, remove a different owner if owner indices diverged, brick an account, or upgrade to an implementation address that is benign on one chain but malicious on another.

## Removing the last owner permanently bricks the wallet
- Location: `src/SmartWallet/MultiOwnable.sol` : `removeOwnerAtIndex`
- Mechanism: `removeOwnerAtIndex` deletes the owner at an index without tracking owner count or preventing removal of the final owner. After the last owner is removed, `_checkOwner()` cannot succeed for any external caller, `_validateSignature` cannot validate an owner index, and `initialize()` cannot be called again because `nextOwnerIndex()` is already nonzero.
- Impact: A wallet can be permanently locked, making `execute`, `executeBatch`, owner recovery, and upgrades unreachable. Any ETH, tokens, or NFTs held by the wallet become irrecoverable.

## Paymaster-only allowance can be withdrawn directly
- Location: `src/MagicSpend/MagicSpend.sol` : `validatePaymasterUserOp`, `withdraw`, `getHash`
- Mechanism: The same `WithdrawRequest` hash authorizes both the paymaster path and the direct `withdraw()` path. In the paymaster path, `amount` is treated as a total budget: `maxCost` is reserved for gas and only `amount - maxCost` is credited as spendable funds. In `withdraw()`, the exact same signed request transfers the full `amount` to `msg.sender`, with no mode/domain field binding the signature to paymaster use.
- Impact: A user holding a request intended to sponsor a UserOperation can call `withdraw()` instead and receive the gas reserve as normal ETH, extracting more spendable funds than the signer intended.

## Zero expiry becomes non-expiring in the paymaster path
- Location: `src/MagicSpend/MagicSpend.sol` : `validatePaymasterUserOp`, `withdraw`
- Mechanism: `withdraw()` treats `expiry == 0` as expired because `block.timestamp > 0`. The paymaster path does not check expiry directly; it packs `expiry` into ERC-4337 `validationData`. EntryPoint v0.6 interprets `validUntil == 0` as `type(uint48).max`, so the same zero-expiry request is valid indefinitely when used as paymaster data.
- Impact: A signed request with `expiry == 0` can be used forever through the paymaster flow, bypassing the apparent expiration semantics of the direct withdrawal path.

## Paymaster refunds gas before postOp gas is counted
- Location: `src/MagicSpend/MagicSpend.sol` : `postOp`
- Mechanism: `postOp` refunds `maxGasCost - actualGasCost` to the account, but EntryPoint v0.6 passes `actualGasCost` before the gas consumed by `postOp` itself is added to final settlement. The final EntryPoint charge to the paymaster deposit is therefore higher than the amount MagicSpend deducts from the user’s signed withdrawal budget.
- Impact: Each sponsored withdrawal under-recovers the paymaster’s own post-operation gas. A user with valid signed requests can repeatedly externalize that postOp gas cost to the paymaster deposit, draining sponsor funds beyond the signed withdrawal budget.

## Multiple validated withdrawals can overcommit the same ETH balance
- Location: `src/MagicSpend/MagicSpend.sol` : `validatePaymasterUserOp`, `postOp`
- Mechanism: Validation checks only `address(this).balance >= withdrawAmount` for the current operation. It does not subtract `_withdrawableETH` already reserved by earlier validated operations in the same EntryPoint bundle. Since EntryPoint validates all operations before executing them, multiple withdrawals can pass against the same ETH balance and later become insolvent during payout.
- Impact: A user with valid signed requests can oversubscribe the paymaster’s local ETH, causing later `postOp` transfers to revert. Because `postOp` asserts against `PostOpMode.postOpReverted`, this can escalate into EntryPoint bundle failure and withdrawal denial of service.

