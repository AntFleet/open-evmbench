# Audit: 2024-06-thorchain

## tx.origin authentication allows draining any RUNE holder
- Location: ethereum/contracts/eth_rune.sol (and chain/ethereum/contracts/eth_rune.sol) : `ETH_RUNE.transferTo`
- Mechanism: `transferTo` calls `_transfer(tx.origin, recipient, amount)`, authenticating the source of funds by `tx.origin` rather than `msg.sender`. Any contract that a RUNE holder is induced to call can, within that same transaction, invoke `ETH_RUNE.transferTo(attacker, victimBalance)`; because `tx.origin` is the victim, the transfer succeeds with no allowance and no per-call consent. The in-code comment acknowledges the “phishing” risk but the function remains a live, unconditional theft primitive.
- Impact: An attacker-controlled contract interacted with by a victim can move the victim’s entire ETH.RUNE balance to itself without any approval.

## ETH transferOut V5 pays from contract balance, unbound to msg.value and ungated
- Location: ethereum/contracts/THORChain_Router.sol (and chain/ duplicate) : `_transferOutV5` / `transferOutV5` / `batchTransferOutV5`
- Mechanism: In the `asset == address(0)` branch, the function sends `transferOutPayload.amount` (`to.send(transferOutPayload.amount)`) drawn from the contract’s own balance, never referencing or validating `msg.value`, and performs no allowance or caller check for ETH. The V4 `transferOut` correctly binds the ETH path to `safeAmount = msg.value`; V5 drops that binding. Consequently any caller can call `transferOutV5({to: self, asset: 0, amount: X})` with `msg.value = 0` and receive `X` of whatever ETH the contract holds. In `batchTransferOutV5`, a caller whose `sum(amount) < msg.value` strands `msg.value - sum(amount)` in the contract, which any third party can then claim via the same unguarded path.
- Impact: Any ETH custodied by the router (e.g. stranded residue from a value/amount-mismatched batch) can be swept by an arbitrary caller, since ETH outflow is neither bound to the value supplied nor gated by vault allowance.

## swapIn forwards the aggregator’s entire balance, allowing theft of stray ETH
- Location: ethereum/contracts/THORChain_Aggregator.sol : `swapIn`; avalanche/src/contracts/AvaxAggregator.sol : `swapIn`
- Mechanism: After the swap, `swapIn` sets `_safeAmount = address(this).balance` and forwards the full contract balance into `depositWithExpiry{value: _safeAmount}(tcVault, ETH, _safeAmount, tcMemo, deadline)`, with `tcVault`/`tcMemo` fully chosen by the caller. The aggregator exposes `receive() external payable {}`, so it can accumulate ETH from accidental transfers or dust left by prior swaps. Because the deposit amount is the whole balance rather than the ETH produced by this caller’s swap, a caller’s `swapIn` sweeps any pre-existing ETH and credits it to the caller’s own `tcVault`/memo.
- Impact: An attacker can call `swapIn` to absorb ETH sitting in the aggregator (not originating from their own swap) and have it credited to a vault/memo of their choosing, stealing stray funds.

## Over-approval plus OZ safeApprove non-zero check bricks swapIn for fee-on-transfer tokens
- Location: avalanche/src/contracts/AvaxAggregator.sol (and chain/ duplicate) : `swapIn`
- Mechanism: `swapIn` does `IERC20(token).safeApprove(address(swapRouter), amount)` (approving the pre-fee `amount`) but swaps `safeAmount = balanceAfter - balanceBefore` (the post-fee amount). The Pangolin router pulls only `safeAmount`, leaving residual allowance `amount - safeAmount > 0` for fee-on-transfer tokens. OpenZeppelin `SafeERC20.safeApprove` reverts when setting a non-zero allowance over an existing non-zero allowance, so the next `swapIn` for the same token reverts at the `safeApprove` call. There is no code path to reset the leftover allowance.
- Impact: A single fee-on-transfer-token swap permanently disables `swapIn` for that token (persistent denial-of-service), since every subsequent call reverts on the stale non-zero approval.

