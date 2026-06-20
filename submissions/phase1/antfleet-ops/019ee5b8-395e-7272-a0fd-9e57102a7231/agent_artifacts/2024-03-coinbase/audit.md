# Audit: 2024-03-coinbase

## Replayable Owner Removal Can Remove the Wrong Owner
- Location: `src/SmartWallet/CoinbaseSmartWallet.sol` : `validateUserOp`, `executeWithoutChainIdValidation`; `src/SmartWallet/MultiOwnable.sol` : `removeOwnerAtIndex`
- Mechanism: `executeWithoutChainIdValidation` verifies a UserOperation hash that omits `block.chainid`, and `removeOwnerAtIndex` is allowed through that replayable path. The signed action removes only an owner index, not the expected owner bytes at that index. If a wallet’s owner index mapping diverges across chains, the same replayed signature can delete a different owner on another chain. The function also does not prevent removal of the last owner.
- Impact: Anyone who observes a valid replayable owner-removal UserOperation can submit it on other chains where the wallet exists, potentially removing the wrong owner or the only usable owner and permanently locking that wallet instance.

## Paymaster Undercharges Users For `postOp` Gas
- Location: `src/MagicSpend/MagicSpend.sol` : `postOp`
- Mechanism: `validatePaymasterUserOp` reserves `maxCost` from the signed withdrawal amount, but `postOp` refunds `maxGasCost - actualGasCost` to the account. In EntryPoint v0.6, the `actualGasCost` passed into `postOp` is computed before the gas consumed by `postOp` itself is added to final settlement. MagicSpend therefore refunds too much and leaves the paymaster deposit to absorb its own `postOp` gas outside the signed budget.
- Impact: A user with valid signed withdrawals can repeatedly make the paymaster pay extra gas beyond the authorized withdrawal amount, slowly draining sponsor funds from the EntryPoint deposit.

## Zero Expiry Becomes Non-Expiring In Paymaster Flow
- Location: `src/MagicSpend/MagicSpend.sol` : `validatePaymasterUserOp`, `withdraw`
- Mechanism: `withdraw()` treats `expiry == 0` as expired because `block.timestamp > 0`. The paymaster path does not perform the same timestamp check; it packs `expiry` into ERC-4337 validation data. EntryPoint v0.6 interprets `validUntil == 0` as no expiry.
- Impact: A signed request with `expiry == 0` cannot be used through `withdraw()`, but can be used indefinitely through the paymaster path, bypassing the intended expiration semantics.

## Multiple Paymaster Requests Can Overcommit The Same ETH Balance
- Location: `src/MagicSpend/MagicSpend.sol` : `validatePaymasterUserOp`, `postOp`
- Mechanism: Validation checks `address(this).balance >= withdrawAmount` per operation, but does not reserve or subtract amounts already credited to `_withdrawableETH` by earlier validations in the same EntryPoint bundle. EntryPoint validates all operations before executing them, so multiple signed withdrawals can pass against the same local ETH balance.
- Impact: A user with multiple valid signed requests can oversubscribe the paymaster’s ETH balance. Later `postOp` payouts can revert due to insufficient ETH, causing sponsored withdrawals or the whole bundle to fail.

