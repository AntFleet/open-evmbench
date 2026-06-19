# Audit: 2024-06-thorchain

## ETH Double-Spend and DoS in batchTransferOutAndCallV5
- Location: `ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5` (called via `batchTransferOutAndCallV5`)
- Mechanism: Inside `_transferOutAndCallV5`, when processing native gas asset swaps (`fromAsset == address(0)`), the contract forwards ETH to the aggregator using `msg.value` (`aggregationPayload.target.call{value: msg.value}`). However, when invoked through the `batchTransferOutAndCallV5` loop, `msg.value` represents the *total* ETH attached to the entire batch transaction, not the individual payload's `fromAmount`. 
- Impact: If a batch contains multiple ETH swap payloads, the first iteration will consume the entire `msg.value`, causing subsequent iterations to fail due to insufficient contract balance and revert the transaction (DoS). More critically, if the Router contract holds leftover ETH reserves (e.g., from dust or accidental transfers), it will successfully send the full `msg.value` multiple times to different targets, draining the Router's ETH reserves via a double-spend accounting error. The implementation must use `aggregationPayload.fromAmount` instead of `msg.value`.

## tx.origin Phishing Vulnerability in ETH_RUNE
- Location: `ethereum/contracts/eth_rune.sol` : `transferTo`
- Mechanism: The `transferTo` function uses `tx.origin` as the sender address (`_transfer(tx.origin, recipient, amount)`) instead of `msg.sender`. While the comments acknowledge this is intended for "approval-less transactions" (like upgrading to native RUNE), it fundamentally breaks the ERC20 security model. If a user interacts with *any* malicious, compromised, or poorly audited smart contract, that contract can arbitrarily call `ETH_RUNE.transferTo(attacker, userBalance)`.
- Impact: Any user holding ETH.RUNE who signs a transaction interacting with a malicious contract (e.g., via a phishing dApp) will have their entire token balance drained without needing to grant any explicit token allowance. 

## Incorrect Approval Amount Causes Reverts with Fee-on-Transfer and Non-Standard Tokens
- Location: `ethereum/contracts/THORChain_Aggregator.sol` (and `avalanche/src/contracts/AvaxAggregator.sol`) : `swapIn`
- Mechanism: The `swapIn` function correctly calculates the actual received token amount (`_safeAmount` / `safeAmount`) to account for fee-on-transfer tokens, but incorrectly calls `safeApprove(token, address(swapRouter), amount)` using the original gross `amount` parameter. 
- Impact: First, approving more than the received balance can cause swap failures if the DEX router strictly validates allowances against balances, or it leaves a dangling allowance. Second, if the aggregator contract holds any residual allowance for the swap router (from dust or a prior interrupted transaction), non-standard tokens like USDT will explicitly revert the `approve` call because they require allowances to be reset to `0` before being set to a new non-zero value. The contract should approve the exact `_safeAmount` and ideally reset the allowance to `0` first (as it correctly does in `swapOutV5`).
