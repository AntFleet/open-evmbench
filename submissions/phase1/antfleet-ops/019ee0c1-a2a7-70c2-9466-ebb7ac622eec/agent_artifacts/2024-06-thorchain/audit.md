# Audit: 2024-06-thorchain

## Router V5 native transfers can spend stale ETH balance
- Location: `chain/ethereum/contracts/THORChain_Router.sol` / `ethereum/contracts/THORChain_Router.sol` : `_transferOutV5`, `transferOutV5`, `batchTransferOutV5`
- Mechanism: For `asset == address(0)`, `_transferOutV5` sends `transferOutPayload.amount` from the router’s current ETH balance, but never checks that `msg.value` supplied that amount. Any ETH left in the router from an overpaid call or forced transfer can therefore be spent by a later caller.
- Impact: An attacker can drain any ETH balance held by the router by calling `transferOutV5` or `batchTransferOutV5` with themselves as `to` and `asset == address(0)`.

## Failed ETH aggregation refunds the aggregator instead of the recipient
- Location: `chain/ethereum/contracts/THORChain_Router.sol` / `ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5`
- Mechanism: In the ETH branch, if `target.swapOutV5(...)` fails, the fallback path sends `msg.value` to `aggregationPayload.target` instead of `aggregationPayload.recipient`. This contradicts the intended fallback behavior and gives the failed aggregator the funds.
- Impact: A malicious or broken aggregator can revert `swapOutV5`, receive the ETH fallback, and keep or rescue funds that should have gone to the user.

## ERC20 aggregation failure strands tokens after allowance is consumed
- Location: `chain/ethereum/contracts/THORChain_Router.sol` / `ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5`
- Mechanism: In the ERC20 branch, the router first decrements the vault allowance and transfers `fromAmount` tokens to `aggregationPayload.target`, then calls `swapOutV5`. The return value `_dexAggSuccess` is ignored, and there is no refund or fallback transfer if the aggregator call fails.
- Impact: A failing or malicious aggregator can leave tokens trapped at the aggregator while the router emits a successful outbound event and permanently consumes the vault allowance.

## Batched ETH aggregation reuses the full transaction value
- Location: `chain/ethereum/contracts/THORChain_Router.sol` / `ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5`, `batchTransferOutAndCallV5`
- Mechanism: Every ETH aggregation payload uses the same global `msg.value`; the router never checks `aggregationPayload.fromAmount`, never sums per-item values, and never decrements value across the batch.
- Impact: ETH aggregation batches can revert after the first item or over-disburse from stale router ETH balance, breaking outbound processing and enabling drain of residual ETH.

## Aggregator swap-in forwards all native balance, not just swap proceeds
- Location: `avalanche/src/contracts/AvaxAggregator.sol` / `chain/avalanche/src/contracts/AvaxAggregator.sol` : `swapIn`; `chain/ethereum/contracts/THORChain_Aggregator.sol` / `ethereum/contracts/THORChain_Aggregator.sol` : `swapIn`
- Mechanism: After swapping, `swapIn` sets the outbound amount to `address(this).balance`. Because the aggregators have payable receivers, any pre-existing ETH/AVAX balance is mixed with the current user’s swap proceeds.
- Impact: Anyone can sweep stuck, donated, or forcibly sent native funds from the aggregator into their chosen THORChain deposit by calling `swapIn` with a small valid swap.

## Public V5 aggregator call can spend stranded ERC20 balances
- Location: `chain/ethereum/contracts/THORChain_Aggregator.sol` / `ethereum/contracts/THORChain_Aggregator.sol` : `swapOutV5`
- Mechanism: The ERC20 branch of `swapOutV5` assumes the aggregator already holds `fromAsset`, approves the DEX, and swaps `fromAmount` to an arbitrary `recipient`. It does not restrict the caller to the THORChain router or bind the call to a prior transfer.
- Impact: Any ERC20 tokens stranded or accidentally transferred to the aggregator can be swapped out by any caller to their own recipient.

## `tx.origin` token transfer allows phishing theft
- Location: `chain/ethereum/contracts/eth_rune.sol` / `ethereum/contracts/eth_rune.sol` : `transferTo`
- Mechanism: `transferTo` transfers tokens from `tx.origin` rather than `msg.sender` and requires no allowance. Any contract called by a victim EOA can invoke `transferTo(attacker, amount)` and make the token contract debit the victim.
- Impact: A phishing contract can steal ETH.RUNE directly from any user who interacts with it.

## Mock swap router ignores supplied amounts
- Location: `chain/ethereum/contracts/sushiswap/SushiRouterSmol.sol` / `ethereum/contracts/sushiswap/SushiRouterSmol.sol` : `swapExactTokensForETH`, `swapExactETHForTokens`
- Mechanism: The router hardcodes output/input handling to `one = 1e18`. `swapExactTokensForETH` pays one ETH regardless of `amountIn`, and `swapExactETHForTokens` deposits exactly one ETH regardless of `msg.value`.
- Impact: If funded or used as a real swap router, callers can drain its ETH/WETH liquidity with minimal input, while overpayments are left stuck and later spendable by others.

