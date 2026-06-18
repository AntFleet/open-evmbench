# Audit: 2024-06-thorchain

## Consensus findings

## tx.origin-authorized, approval-less token drain in ETH.RUNE
*(consensus)*
- Location: `ethereum/contracts/eth_rune.sol` and `chain/ethereum/contracts/eth_rune.sol` : `ETH_RUNE.transferTo(address recipient, uint256 amount)` (around lines 159–162)
- Mechanism: `transferTo` calls `_transfer(tx.origin, recipient, amount)`, debiting `tx.origin` instead of `msg.sender`, with no allowance check and no relationship between `tx.origin` and `msg.sender`; `recipient` and `amount` are fully caller-controlled. Any contract invoked inside the same transaction as a RUNE holder can call `RUNE.transferTo(attacker, holderBalance)` and the transfer is authorized purely because the victim is `tx.origin`.
- Impact: Any contract a RUNE holder interacts with (a "swap UI" helper, an airdrop claimer, a malicious approval-less dApp, or a token with a hook) can silently sweep the holder's entire ETH.RUNE balance with one nested call to an attacker-controlled recipient. It needs no prior approval from the victim — strictly worse than the "infinite approval" pattern the dev comment compares it to.

## swapIn forwards the aggregator's entire native balance instead of the measured swap output
*(consensus)*
- Location: `ethereum/contracts/THORChain_Aggregator.sol` and `chain/ethereum/contracts/THORChain_Aggregator.sol` : `swapIn(...)` (around lines 95–127; `_safeAmount = address(this).balance; iROUTER(tcRouter).depositWithExpiry{value: _safeAmount}(...)`); `avalanche/src/contracts/AvaxAggregator.sol` and `chain/avalanche/src/contracts/AvaxAggregator.sol` : `swapIn(...)` (around lines 57–98; `safeAmount = address(this).balance; ... depositWithExpiry{value: safeAmount}`); identical in `THORChain_Failing_Aggregator.sol` : `swapIn`.
- Mechanism: After swapping the caller's tokens to the native asset, `swapIn` sets the outbound deposit amount to `address(this).balance` — the *whole* contract balance — rather than measuring only the native asset received during the current call. The deposit credits a fully caller-controlled `tcVault`/`tcMemo` (router/vault and memo path). With an open `receive()` and aggregators designed to hold no native balance between calls, any pre-existing native balance (accidental sends, forced sends, dust/residue) is attributed to whoever calls `swapIn` next.
- Impact: An attacker performs a small/dust `swapIn` with their own `tcVault`/`tcMemo`; the swap yields ~0 but the contract forwards its full native balance to THORChain credited to the attacker's memo. Any ETH/AVAX stranded in the aggregator is stealable by an arbitrary caller. The ETH aggregator at least has `onlyOwner rescueFunds`; `AvaxAggregator` has no rescue path at all, so stranded AVAX is only recoverable via this theft vector.

## Additional findings (single-reviewer)

## batchTransferOutAndCallV5 reuses msg.value on every loop iteration
*(Reviewer A only)*
- Location: `ethereum/contracts/THORChain_Router.sol` and `chain/ethereum/contracts/THORChain_Router.sol` : `batchTransferOutAndCallV5(...)` → `_transferOutAndCallV5(...)` native-asset branch (`aggregationPayload.target.call{value: msg.value}(...)`, and the bounce `payable(...).send(msg.value)`)
- Mechanism: `_transferOutAndCallV5` always uses `msg.value` (transaction-wide, constant across iterations) as the amount to forward, instead of a per-element amount. In a batch with N native-asset payloads, the loop attempts to send `msg.value` N times — `N * msg.value` total — while only `msg.value` was supplied. Contrast `batchTransferOutV5`/`_transferOutV5`, which correctly use the per-element `transferOutPayload.amount`. The single-call path also emits an event recording `msg.value` rather than any per-payload amount, so per-leg accounting is wrong for batches.
- Impact: For any batch with more than one native-asset entry, every entry after the first is funded from whatever native balance the contract happens to hold rather than the caller's supplied value; if the router ever holds native balance it is over-spent/misdirected, and otherwise the second send fails and reverts the whole batch (DoS of multi-leg native batches). Latent fund-safety/accounting bug — a per-leg amount field exists conceptually but is never honored.

## AvaxAggregator.swapIn approves `amount` but swaps `safeAmount`, bricking fee-on-transfer tokens
*(Reviewer A only)*
- Location: `avalanche/src/contracts/AvaxAggregator.sol` and `chain/avalanche/src/contracts/AvaxAggregator.sol` : `swapIn(...)` (`IERC20(token).safeApprove(address(swapRouter), amount)` followed by computing `safeAmount = balanceOf - startBal` and `swapExactTokensForAVAX(safeAmount, ...)`)
- Mechanism: Uses OpenZeppelin `SafeERC20.safeApprove`, which reverts when changing a non-zero allowance to another non-zero value. It approves the requested `amount` but the swap only consumes the actually-received `safeAmount`. For a fee-on-transfer token, `safeAmount < amount`, leaving a residual allowance (`amount - safeAmount`) after the swap. The next `swapIn` for that token then calls `safeApprove(amount)` against a non-zero residual allowance and reverts, with no path to reset the allowance.
- Impact: Permanent denial-of-service of `swapIn` for any fee-on-transfer token via this aggregator after the first use, plus a standing residual allowance to the swap router. No direct theft, but a genuine functional/state-consistency flaw caused by approving the requested amount instead of the measured `safeAmount`.

## transferOut / _transferOutV5 emit a success event for funds that bounced back to the vault
*(Reviewer A only)*
- Location: `ethereum/contracts/THORChain_Router.sol`, `chain/ethereum/contracts/THORChain_Router.sol`, and `AvaxRouter.sol` : `transferOut(...)` and `_transferOutV5(...)` native-asset branches — on `to.send` failure the value is returned to `msg.sender`, then `emit TransferOut(msg.sender, to, asset, safeAmount, memo)` reports it as delivered to `to`
- Mechanism: When the outbound native `send` to `to` fails (recipient reverts or exceeds the 2300-gas stipend), the code bounces the value back to `msg.sender` (the vault) but still emits `TransferOut` with the original `to` and the full amount. The event — the off-chain settlement source of truth — records a delivery that did not occur (the value is back in the vault).
- Impact: An off-chain observer that finalizes outbounds purely on `TransferOut` marks the transfer complete while the asset actually remains in the vault. Because the bounce returns to the same vault, solvency is preserved, so this is an observability/accounting correctness issue rather than direct theft; an attacker can deliberately trigger the bounce by being a reverting/gas-burning recipient.

## Failed V5 ETH aggregation sends funds to the aggregator target instead of the recipient
*(Reviewer B only)*
- Location: `chain/ethereum/contracts/THORChain_Router.sol` and `ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5` (ETH branch, around lines 296–339)
- Mechanism: When `swapOutV5` fails for a native ETH aggregation, the fallback path sends `msg.value` to `aggregationPayload.target` instead of `aggregationPayload.recipient`, and the event is still emitted as if the outbound aggregation completed.
- Impact: A failing or malicious aggregator target that reverts `swapOutV5` but accepts ETH can receive the full outbound amount, leaving the intended recipient unpaid. Precondition: the vault routes an ETH `transferOutAndCallV5` to that target.

## Failed V5 ERC20 aggregation locks or steals tokens
*(Reviewer B only)*
- Location: `chain/ethereum/contracts/THORChain_Router.sol` and `ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5` (ERC20 branch, around lines 340–385)
- Mechanism: The router decrements the vault allowance and transfers ERC20 tokens to `aggregationPayload.target` before calling `swapOutV5`, but it stores `_dexAggSuccess` and never checks it or refunds on failure. A reverting target keeps the already-transferred tokens while the router emits a successful-looking event.
- Impact: A malicious or incompatible aggregator can receive ERC20 outbound funds and fail the swap, causing the recipient to receive nothing while the vault allowance is consumed.

## Public swapOutV5 can drain aggregator ERC20 balances
*(Reviewer B only)*
- Location: `chain/ethereum/contracts/THORChain_Aggregator.sol` and `ethereum/contracts/THORChain_Aggregator.sol` : `swapOutV5` (around lines 147–203)
- Mechanism: `swapOutV5` is public and, for ERC20 inputs, approves the swap router for `fromAmount` and swaps tokens from the aggregator contract to an arbitrary `recipient` without verifying that the caller is the THORChain router or that the tokens were just delivered for this call.
- Impact: Anyone can drain any ERC20 balance stranded in the aggregator — including tokens left there after a failed V5 router aggregation — by swapping them to an attacker-controlled recipient.

## Public V5 native transfer can spend stranded router ETH
*(Reviewer B only)*
- Location: `chain/ethereum/contracts/THORChain_Router.sol` and `ethereum/contracts/THORChain_Router.sol` : `transferOutV5` / `_transferOutV5` (around lines 199–237)
- Mechanism: The V5 native-asset branch sends `transferOutPayload.amount` from the router's ETH balance and does not require `msg.value == transferOutPayload.amount`. Unlike ERC20 transfers, there is no allowance check for native ETH.
- Impact: Anyone can drain ETH accidentally or forcibly held by the router by calling `transferOutV5` with `asset == address(0)` and `to` set to themselves.

---

**Merge notes:** Both reviewers independently flagged the ETH.RUNE `tx.origin` drain and the `swapIn` whole-balance deposit — these are the two consensus findings (same root cause and code path, merged with the most specific location/line and mechanism detail from each). The remaining seven are single-reviewer. Note that Reviewer A's `_transferOutAndCallV5` finding (msg.value reused across batch iterations) and Reviewer B's `_transferOutAndCallV5` findings (wrong destination/no refund on `swapOutV5` failure, ETH and ERC20 branches) touch the same function but describe **distinct** root causes, so they are kept separate rather than collapsed. Likewise, Reviewer A's event-desync in `_transferOutV5` and Reviewer B's missing-`msg.value`-check in `_transferOutV5` are different mechanisms in the same function and are kept separate.

