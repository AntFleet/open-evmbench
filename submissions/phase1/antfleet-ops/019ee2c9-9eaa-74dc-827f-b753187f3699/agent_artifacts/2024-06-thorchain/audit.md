# Audit: 2024-06-thorchain

## V5 ERC20 outbound swaps fail open after the router has already handed over the tokens
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5` (duplicated in `ethereum/contracts/THORChain_Router.sol`)
- Mechanism: In the ERC20 branch, the router first decrements `_vaultAllowance[msg.sender][fromAsset]`, then transfers `fromAmount` tokens to `aggregationPayload.target`, and only afterwards calls `swapOutV5` on that target. The result of that call is stored in `_dexAggSuccess` and then ignored. Because the token transfer happens before the external call and the failure path does not revert or compensate, any revert, no-op, or partial failure inside the aggregator leaves the tokens sitting in the target contract while the router still treats the operation as complete.
- Impact: A buggy or malicious aggregator can keep all ERC20 funds sent through `transferOutAndCallV5`; the intended recipient receives nothing, while the vault’s allowance is permanently reduced.

## V5 ETH fallback sends funds to the aggregator instead of the intended recipient
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5` (duplicated in `ethereum/contracts/THORChain_Router.sol`)
- Mechanism: In the `fromAsset == address(0)` branch, if the `swapOutV5` call fails, the fallback path is supposed to send the gas asset to the recipient. Instead, the code executes `payable(aggregationPayload.target).send(msg.value)`. That means the failing aggregator itself receives the ETH on the failure path, and only if that send also fails does the router bounce the ETH back to the calling vault.
- Impact: Any aggregator that reverts or intentionally fails can still receive and keep the full outbound ETH amount, causing direct loss of vault funds.

## Stranded aggregator balances are permissionlessly claimable by arbitrary callers
- Location: `chain/ethereum/contracts/THORChain_Aggregator.sol` : `swapIn`, `swapOutV5`; `chain/avalanche/src/contracts/AvaxAggregator.sol` : `swapIn` (duplicated under `ethereum/contracts/...` and `avalanche/src/...`)
- Mechanism: The aggregator code does not isolate per-call balances. In `swapIn`, after the swap it uses `address(this).balance` as the amount to deposit, so any ETH/AVAX already sitting in the contract is swept into the current caller’s THORChain deposit. In the ERC20 branch of `swapOutV5`, the function never verifies that `fromAmount` was supplied by the current call; it simply approves and swaps whatever `fromAsset` balance the contract already holds to a caller-chosen `recipient`. Because these functions are public, any pre-existing contract balance becomes claimable by the next caller.
- Impact: Any ETH/AVAX/ERC20 stranded in an aggregator contract, whether from accidental transfers, forced sends, or failed router flows, can be stolen by an arbitrary external caller.

## `tx.origin` authorization allows phishing-based ETH.RUNE theft
- Location: `chain/ethereum/contracts/eth_rune.sol` : `transferTo` (duplicated in `ethereum/contracts/eth_rune.sol`)
- Mechanism: `transferTo` transfers tokens from `tx.origin` instead of `msg.sender`. That lets an intermediate contract invoke `transferTo(attacker, amount)` during any transaction initiated by a token holder, and the token contract will debit the holder’s balance even though the holder never directly called the token or approved the transfer.
- Impact: A malicious dapp or helper contract can steal arbitrary ETH.RUNE balances from users who interact with it, without needing allowance first.

I did not count the intentionally adversarial/demo contracts such as `Evil*`, `Steal*`, and `THORChain_Failing_Aggregator` as protocol findings.

