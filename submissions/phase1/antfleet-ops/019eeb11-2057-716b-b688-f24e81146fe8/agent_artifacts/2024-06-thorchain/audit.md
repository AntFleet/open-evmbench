# Audit: 2024-06-thorchain
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## tx.origin authorization in `ETH_RUNE.transferTo`
*(consensus, 6 of 6 reports)*
- Location: `ethereum/contracts/eth_rune.sol` (and `chain/ethereum/contracts/eth_rune.sol`) : `transferTo`
- Mechanism: `transferTo(address recipient, uint256 amount)` calls `_transfer(tx.origin, recipient, amount)` with no allowance check and no `msg.sender` restriction. Authorization is derived from `tx.origin` (the transaction's originating EOA) rather than an approval or the calling contract. Any intermediary contract a victim transaction passes through can call `transferTo(attacker, victimBalance)`.
- Impact: Full drain of any RUNE holder's balance via a single interaction with a malicious/compromised contract (classic tx.origin phishing). No prior approval is needed; merely transacting through a hostile contract exposes the holder's entire ETH.RUNE balance.
- Reviewer disagreement: none — all reports flag it; the in-code comment acknowledges the design but reports agree it is a live, externally exploitable drain.

## `swapIn` forwards the aggregator's entire native balance to a caller-controlled destination
*(consensus, 6 of 6 reports)*
- Location: `ethereum/contracts/THORChain_Aggregator.sol`, `chain/ethereum/contracts/THORChain_Aggregator.sol`, `THORChain_Failing_Aggregator.sol`, `avalanche/src/contracts/AvaxAggregator.sol`, `chain/avalanche/src/contracts/AvaxAggregator.sol` : `swapIn`
- Mechanism: After the token→native swap, `swapIn` sets the outbound amount to `address(this).balance` (the whole contract balance, not the swap delta) and forwards it via `iROUTER(tcRouter).depositWithExpiry{value: _safeAmount}(payable(tcVault), ETH, ...)`. `tcRouter`, `tcVault`, and `tcMemo` are unvalidated caller inputs, and the contract has a payable `receive()`, so any idle native funds are treated as the current caller's proceeds.
- Impact: Anyone can sweep stranded/idle native (ETH/AVAX) out of the aggregator — dust, forced sends, mis-sent funds, or funds left by failed flows — by performing a minimal `swapIn` with `amountOutMin = 0` and a `tcRouter`/`tcVault`/`tcMemo` that credits the attacker. Balance-gated theft of other users' stranded value.
- Reviewer disagreement: none.

## Permissionless `swapOutV5` / `swapOut` (ERC20 branch) drains stranded token balances
*(consensus, 5 of 6 reports)*
- Location: `ethereum/contracts/THORChain_Aggregator.sol` (and `chain/ethereum/...`) : `swapOutV5` (ERC20 branch) and `swapOut`
- Mechanism: `swapOutV5` is `public payable` with no access control and does not verify `msg.sender` is the router or that `fromAmount` matches a same-tx inflow. The ERC20 branch does `safeApprove(fromAsset, swapRouter, fromAmount)` then `swapExactTokensForETH(fromAmount, amountOutMin, [fromAsset, WETH], recipient, ...)`, pulling `fromAsset` from the aggregator itself and sending ETH to a caller-chosen `recipient`. `fromAsset`, `fromAmount`, `amountOutMin`, and `recipient` are all attacker-controlled.
- Impact: Any ERC20 sitting in the aggregator (e.g. tokens stranded by a failed `_transferOutAndCallV5`, or donations/mis-sends) can be swapped to ETH and sent to an attacker by calling `swapOutV5(strayToken, strayAmount, anyToAsset, attacker, 0, "", "")`.
- Reviewer disagreement: none explicit (gpt-5.5 shot 1 simply did not surface this aggregator path, but it did not defend it).

## Router `_transferOutAndCallV5` ERC20 branch strands tokens on failed aggregation
*(consensus, 5 of 6 reports)*
- Location: `ethereum/contracts/THORChain_Router.sol` (and `chain/ethereum/...`) : `_transferOutAndCallV5` (ERC20 branch), `transferOutAndCallV5`, `batchTransferOutAndCallV5`
- Mechanism: The ERC20 branch decrements the vault allowance and transfers `fromAmount` of `fromAsset` to `aggregationPayload.target`, then calls `swapOutV5`. The result is stored in `_dexAggSuccess` but never checked; there is no fallback transfer, refund, or revert when the target fails.
- Impact: A malicious or failing target retains the ERC20 tokens while the router still emits `TransferOutAndCallV5` as if completed. Vault allowance is burned and the recipient's output is stranded at the target (and subsequently drainable via the public `swapOutV5` path above).
- Reviewer disagreement: none — two opus reports describe this as the precondition that makes the aggregator drain reachable; three gpt reports list it as a standalone loss-of-funds defect.

## V5 ETH fallback refunds the failing target instead of the recipient
*(consensus, 4 of 6 reports)*
- Location: `ethereum/contracts/THORChain_Router.sol` (and `chain/ethereum/...`) : `_transferOutAndCallV5` (gas-asset branch, `if (!swapOutSuccess)`)
- Mechanism: In the native-asset branch, when `swapOutV5` returns false / reverts, the code executes `payable(aggregationPayload.target).send(msg.value)` — refunding the aggregator `target`, not `aggregationPayload.recipient`. The inline comment ("just send the recipient the gas asset") and the V4 `transferOutAndCall` path (which sends to `to`) confirm the intended behavior is to refund the end recipient. Because the aggregator has a payable `receive()`, the 2300-gas `send` succeeds and the funds lodge in the aggregator.
- Impact: Every outbound V5 ETH swap that fails at the aggregator misdirects the user's outbound ETH into the aggregator instead of returning it to the user. The recipient gets nothing; a malicious/broken target can deliberately revert `swapOutV5` to capture the ETH (or it becomes idle balance any party can sweep via `swapIn`).
- Reviewer disagreement: none.

## Batched V5 ETH aggregation reuses the full `msg.value` for every item
*(consensus, 3 of 6 reports)*
- Location: `ethereum/contracts/THORChain_Router.sol` (and `chain/ethereum/...`) : `_transferOutAndCallV5` (native branch) / `batchTransferOutAndCallV5`
- Mechanism: The ETH branch ignores `aggregationPayload.fromAmount` and uses the transaction-wide `msg.value` for the low-level call, the fallback, and the emitted amount. In `batchTransferOutAndCallV5`, every payload is processed with the same full `msg.value` rather than its own per-item amount.
- Impact: In a batched ETH outbound, the first successful target/recipient can receive the entire batch value while later items revert or become underfunded. An attacker who can get their ETH outbound ordered first can capture other batched recipients' ETH.
- Reviewer disagreement: opus shot 3 acknowledged the same code path but classified it as "a correctness wart but not drainable," reasoning the router forwards ETH synchronously and never accumulates a balance.

## Public V5 `transferOutV5` can drain idle router ETH
*(consensus, 2 of 6 reports)*
- Location: `ethereum/contracts/THORChain_Router.sol` (and `chain/ethereum/...`) : `_transferOutV5` / `transferOutV5` / `batchTransferOutV5`
- Mechanism: The native-asset branch sends `transferOutPayload.amount` from the router's own ETH balance without requiring `msg.value == transferOutPayload.amount`. Unlike the V4 `transferOut`, the sent amount is caller-controlled and not bound to the value supplied with the call.
- Impact: Any ETH left in the router (overfunded V5 calls, forced transfers, accounting leftovers) can be swept by any caller invoking `transferOutV5` with `asset == address(0)` and `to` set to themselves.
- Reviewer disagreement: opus shot 3 argued the router's `transferOut`/`_deposit` ETH paths never let it accumulate ETH (no `receive`/`fallback`, funds forwarded synchronously), so there is no idle ETH to drain.

## Minority findings

## Mock `SushiRouterSmol` pays fixed output unrelated to input
*(minority, 1 of 6 reports)* *(conflicting reviews: 1 of 6 reports explicitly classified this code path as a non-production mock)*
- Location: `ethereum/contracts/sushiswap/SushiRouterSmol.sol` (and `chain/ethereum/...`) : `swapExactTokensForETH`, `swapExactETHForTokens`
- Mechanism: Both functions hard-code `amounts = [1e18]` and do not price against reserves, `amountIn`, or `msg.value`. `swapExactTokensForETH` accepts arbitrary `amountIn` of `path[0]` and pays exactly 1 ETH if the contract holds WETH; `swapExactETHForTokens` wraps exactly 1 ETH and transfers exactly 1e18 of `path[1]`.
- Impact: If deployed with real balances, an attacker can drain 1 ETH/WETH or 1e18 output tokens per call using worthless or insufficient input. Precondition: the router holds the relevant balance.
- Reviewer disagreement: opus shot 1 explicitly named `SushiRouterSmol` as a test/reference mock "not a production target" and treated it as out of scope (opus shot 3 likewise scoped it out as a non-business-logic fixture).

## `AvaxAggregator.swapIn` bricks fee-on-transfer tokens via OZ `safeApprove`
*(minority, 1 of 6 reports)*
- Location: `avalanche/src/contracts/AvaxAggregator.sol` (and `chain/avalanche/...`) : `swapIn` (`IERC20(token).safeApprove(address(swapRouter), amount)`)
- Mechanism: `swapIn` approves `amount` (the requested input) while only `safeAmount` (the actual received delta) is swapped. For a fee-on-transfer token `safeAmount < amount`, leaving a non-zero residual allowance. OpenZeppelin `SafeERC20.safeApprove` reverts when moving from a non-zero allowance to another non-zero value, so the next `swapIn` for that token reverts at the approve step. (The Ethereum aggregator uses a low-level overwriting approve and is not affected.)
- Impact: Any fee-on-transfer token routed through `AvaxAggregator` can be swapped at most once; thereafter `swapIn` for that token permanently reverts — a denial of service for that asset path with no on-chain allowance-reset remediation.
- Reviewer disagreement: none — no other report addressed this code path.

---

**Reconciliation check:** 9 distinct findings identified across all six reports by (code path + root cause) — A tx.origin transfer, B swapIn native sweep, C aggregator swapOutV5 ERC20 drain, D V5 ETH fallback-to-target, E router V5 ERC20 strand-on-failure, F batched V5 msg.value reuse, G transferOutV5 idle-router-ETH drain, H SushiRouterSmol mock pricing, I AvaxAggregator safeApprove DoS. 9 findings emitted (7 consensus + 2 minority). No findings dropped; the two opus reports' net-zero `_routerDeposit` / sound-`_vaultAllowance` / reentrancy-blocked claims were explicit non-findings claimed by no report and were not invented as findings.

