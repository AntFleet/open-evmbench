# Audit: 2024-06-thorchain

## `_transferOutAndCallV5` sends ETH to wrong address on swap failure
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5` (ETH path)
- Mechanism: When the `swapOutV5` call to the aggregator target fails, the fallback sends `msg.value` to `aggregationPayload.target` (the aggregator contract) instead of `aggregationPayload.recipient` (the user). The code comment even says "send the recipient the gas asset" but the code sends to `target`. This contradicts the V4 `transferOutAndCall` which correctly sends to `to` (the recipient) on failure.
- Impact: When an ETH swap through the aggregator fails, the user's ETH is sent to the aggregator contract instead of being returned to the user. Funds become stuck at the aggregator address and are only recoverable via the aggregator's owner-gated `rescueFunds`.

## `_transferOutAndCallV5` ERC20 path silently loses funds on aggregator failure
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5` (ERC20 path)
- Mechanism: In the ERC20 branch, vault allowance is decremented and tokens are transferred to the aggregator (`target`) via `transfer()`. Then `swapOutV5` is called on the aggregator via a low-level `.call`. The return value `_dexAggSuccess` is **never checked** — the function emits `TransferOutAndCallV5` and returns successfully regardless of whether the swap succeeded. The tokens have already left the router and are now stuck at the aggregator if the swap failed.
- Impact: If the aggregator's swap fails for any reason (insufficient liquidity, router paused, malformed call), the ERC20 tokens are permanently stuck at the aggregator address. Bifrost observes the emitted event and considers the outbound transfer complete, so the user never receives their funds and the protocol cannot retry.

## `ETH_RUNE.transferTo` uses `tx.origin` allowing token theft via phishing
- Location: `chain/ethereum/contracts/eth_rune.sol` : `transferTo`
- Mechanism: `transferTo` transfers tokens from `tx.origin` (the EOA that initiated the transaction) rather than `msg.sender`. If a user interacts with a malicious contract that calls `transferTo(attacker, balance)`, the attacker can steal all of the user's ETH.RUNE tokens without any approval, because `tx.origin` is the user's EOA.
- Impact: Any malicious contract that a RUNE holder interacts with can drain their entire ETH.RUNE balance. This is an active phishing vector, not just a theoretical concern.

## Aggregator `swapIn` approves `amount` instead of `safeAmount`, leaving residual approval
- Location: `avalanche/src/contracts/AvaxAggregator.sol` : `swapIn`, `chain/ethereum/contracts/THORChain_Aggregator.sol` : `swapIn`
- Mechanism: The aggregator calls `safeApprove(swapRouter, amount)` using the user-specified `amount`, but then only swaps `safeAmount` (the actual received amount after transfer fees). For fee-on-transfer tokens, `safeAmount < amount`, leaving a residual approval of `amount - safeAmount` on the swapRouter. This approval is never reset to zero.
- Impact: A compromised or malicious swapRouter can steal the residual approved tokens from the aggregator. Even without a compromised router, the dangling approval accumulates across calls and could be exploited if the swapRouter is later upgraded or compromised.

## `swapOutV5` accepts and traps ETH in the ERC20 swap path
- Location: `chain/ethereum/contracts/THORChain_Aggregator.sol` : `swapOutV5`
- Mechanism: `swapOutV5` is `payable`. When `fromAsset != address(0)` (ERC20 path), `msg.value` is never used or forwarded — it silently remains in the contract. The ETH path and ERC20 path are distinguished by `fromAsset == address(0)`, but nothing prevents a caller from sending ETH alongside an ERC20 swap.
- Impact: ETH sent with an ERC20 `swapOutV5` call is permanently stuck in the aggregator contract. Only the owner can recover it via `rescueFunds`. When called through the router's `transferOutAndCallV5` this won't happen (the router only sends ETH in the native path), but direct callers can accidentally lock funds.
