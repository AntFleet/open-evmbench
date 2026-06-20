# Audit: 2024-06-thorchain

## ETH_RUNE `transferTo` Drains `tx.origin`
- Location: `ethereum/contracts/eth_rune.sol : transferTo`; `chain/ethereum/contracts/eth_rune.sol : transferTo`
- Mechanism: `transferTo` debits `tx.origin` instead of `msg.sender` and requires no approval or trusted caller. Any contract that a token holder interacts with can call `transferTo(attacker, amount)` and make the token contract transfer from the EOA origin.
- Impact: A phishing contract can drain a victim’s ETH_RUNE balance in the same transaction the victim uses to interact with it.

## Failed ERC20 V5 Aggregator Calls Still Consume Vault Allowance
- Location: `ethereum/contracts/THORChain_Router.sol : _transferOutAndCallV5`; `chain/ethereum/contracts/THORChain_Router.sol : _transferOutAndCallV5`
- Mechanism: In the ERC20 branch, the router decrements `_vaultAllowance`, transfers `fromAsset` to `aggregationPayload.target`, then calls `swapOutV5`. The returned `_dexAggSuccess` is ignored, so a reverted or failed aggregator call does not revert or trigger fallback recovery, and the router still emits `TransferOutAndCallV5`.
- Impact: A failing or malicious aggregator can retain outbound ERC20 funds while the recipient receives nothing and the vault allowance is consumed.

## Failed Native V5 Aggregator Fallback Pays The Target
- Location: `ethereum/contracts/THORChain_Router.sol : _transferOutAndCallV5`; `chain/ethereum/contracts/THORChain_Router.sol : _transferOutAndCallV5`
- Mechanism: In the native ETH branch, if `swapOutV5` fails, the fallback sends `msg.value` to `aggregationPayload.target` instead of `aggregationPayload.recipient`.
- Impact: An aggregator that reverts in `swapOutV5` but accepts plain ETH can capture the outbound funds; otherwise the recipient is not paid even though the router emits the outbound event.

## V5 Native Transfers Can Drain Router ETH Balance
- Location: `ethereum/contracts/THORChain_Router.sol : _transferOutV5`; `chain/ethereum/contracts/THORChain_Router.sol : _transferOutV5`
- Mechanism: For `asset == address(0)`, `_transferOutV5` sends `transferOutPayload.amount` from the router’s balance without requiring that `msg.value` equals the amount, and native assets have no vault allowance accounting.
- Impact: Anyone can drain ETH accidentally overpaid, left over, or force-sent to the router by calling `transferOutV5` with themselves as `to`, `asset = address(0)`, and `msg.value = 0`.

## Batched Native Aggregator Calls Reuse The Same `msg.value`
- Location: `ethereum/contracts/THORChain_Router.sol : batchTransferOutAndCallV5`; `chain/ethereum/contracts/THORChain_Router.sol : batchTransferOutAndCallV5`
- Mechanism: `_transferOutAndCallV5` ignores `aggregationPayload.fromAmount` for native ETH and uses the global `msg.value`. In a batch, every native payload therefore attempts to use the same full `msg.value` rather than a per-item amount.
- Impact: Batched native outbounds can overpay the first target, revert subsequent items, or spend pre-existing router ETH balance if one exists.

## Public `swapOutV5` Can Spend Stranded Aggregator Tokens
- Location: `ethereum/contracts/THORChain_Aggregator.sol : swapOutV5`; `chain/ethereum/contracts/THORChain_Aggregator.sol : swapOutV5`
- Mechanism: For `fromAsset != address(0)`, `swapOutV5` assumes tokens were just transferred in by the router, but the function is public and does not authenticate the caller or account for a fresh balance delta. It approves `fromAmount` from the aggregator’s current token balance and sends swap proceeds to caller-controlled `recipient`.
- Impact: Any ERC20 tokens stranded in the aggregator, including tokens left by a failed router V5 aggregator call, can be swapped out by anyone to themselves.

## `swapIn` Sweeps Existing Native Balance
- Location: `ethereum/contracts/THORChain_Aggregator.sol : swapIn`; `chain/ethereum/contracts/THORChain_Aggregator.sol : swapIn`; `avalanche/src/contracts/AvaxAggregator.sol : swapIn`; `chain/avalanche/src/contracts/AvaxAggregator.sol : swapIn`
- Mechanism: After the DEX swap, the aggregator sets the deposit amount to `address(this).balance` instead of the ETH/AVAX delta produced by the current swap. Because the contracts can receive native funds and the THORChain router/vault parameters are caller-controlled, any pre-existing native balance is included in the next caller’s deposit.
- Impact: An attacker can steal ETH/AVAX accidentally sent or force-sent to the aggregator by performing a small `swapIn` and routing the entire native balance to a vault/router they control.

