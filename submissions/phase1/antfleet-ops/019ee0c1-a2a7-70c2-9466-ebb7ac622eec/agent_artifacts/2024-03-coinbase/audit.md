# Audit: 2024-03-coinbase

## Cross-chain replay of privileged wallet actions
- Location: `src/SmartWallet/CoinbaseSmartWallet.sol` : `validateUserOp`, `executeWithoutChainIdValidation`, `canSkipChainIdValidation`
- Mechanism: When calldata targets `executeWithoutChainIdValidation`, the wallet verifies `getUserOpHashWithoutChainId(userOp)`, intentionally removing `block.chainid`. The selector allowlist includes owner mutations and `UUPSUpgradeable.upgradeToAndCall`, so one valid signature authorizes the same privileged action on every chain where the wallet has the same address.
- Impact: Anyone who observes one signed replayable operation can replay it on other chains. This can remove/add different owners if owner indices diverge, brick a wallet by removing its only owner, or upgrade the wallet to an implementation address that is benign on one chain but malicious on another, enabling full account takeover on the replayed chain.

## Paymaster gas budget can be withdrawn as user funds
- Location: `src/MagicSpend/MagicSpend.sol` : `validatePaymasterUserOp`, `withdraw`, `getHash`
- Mechanism: The same `WithdrawRequest` hash is accepted by both the ERC-4337 paymaster path and the direct `withdraw()` path. In `validatePaymasterUserOp`, `amount` is treated as a total budget where `maxCost` is reserved for gas and only `amount - maxCost` becomes withdrawable. In `withdraw()`, the exact same signed request transfers the full `amount` directly to the caller, with no domain separator or mode field distinguishing “paymaster sponsorship” from “direct withdrawal.”
- Impact: A user holding a request intended to sponsor gas can bypass the paymaster flow and call `withdraw()` instead, receiving the gas reserve as spendable ETH and draining more contract funds than the signer intended.

