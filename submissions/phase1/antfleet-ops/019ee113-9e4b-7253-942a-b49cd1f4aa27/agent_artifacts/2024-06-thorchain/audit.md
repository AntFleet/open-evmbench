# Audit: 2024-06-thorchain

# Security Audit Findings

## Incorrect ETH Fallback Recipient in `transferOutAndCallV5`
- **Location**: `chain/ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5` (ETH branch)
- **Mechanism**: When `swapOutV5` reverts on the aggregator, the fallback `payable(aggregationPayload.target).send(msg.value)` sends the ETH to the aggregator (`target`) instead of the intended `recipient`. This is inconsistent with both the V4 implementation (`transferOutAndCall`) and the Avalanche `AvaxRouter.transferOutAndCall`, both of which correctly forward the gas asset to `to`/`recipient` on swap failure. A malicious or buggy aggregator that rejects the fallback `send` causes the ETH to bounce back to the vault rather than reaching the user, while a malicious aggregator can simply swallow the ETH.
- **Impact**: Outbound swap ETH can be misdirected to the aggregator contract instead of the intended recipient, enabling theft or permanent loss of user funds when the aggregator is malicious or its fallback is broken.

## Fee-on-Transfer Accounting Error in V5 Transfer Functions
- **Location**: `chain/ethereum/contracts/THORChain_Router.sol` : `_transferOutV5` and `_transferOutAndCallV5` (ERC20 branch)
- **Mechanism**: The vault's allowance is decremented by the *requested* amount (`transferOutPayload.amount` / `aggregationPayload.fromAmount`) before the low-level `transfer` call is made. For tokens that charge a transfer fee (or any token whose `transfer` delivers less than `amount` to the recipient), the actual on-chain movement is smaller than what was booked against `_vaultAllowance[msg.sender][asset]`. The V4 path doesn't have this issue because it doesn't introduce an intermediate decrement step for outbound aggregator transfers, and `safeTransferFrom` correctly measures the *received* balance delta.
- **Impact**: Every fee-on-transfer ERC20 outbound burns a portion of the vault's recorded allowance while the tokens that actually moved are smaller. Over time the accounting drifts, so the on-chain `_vaultAllowance` becomes smaller than the real residual balance — directly enabling loss/withdrawal of funds (or, conversely, leaving the vault unable to spend tokens it still controls).

## Hard-Coded `type(uint).max` Deadline in Outbound Swaps
- **Location**: 
  - `chain/avalanche/src/contracts/AvaxAggregator.sol` : `swapOut`
  - `chain/ethereum/contracts/THORChain_Aggregator.sol` : `swapOut` and `swapOutV5` (both ETH and ERC20 branches)
- **Mechanism**: The aggregator hard-codes the DEX `deadline` to `type(uint256).max` / `type(uint).max`, meaning the swap remains valid forever. A validator/MEV bot can hold or delay the swap until the price moves adversely, or sandwich the transaction. The `swapIn` path correctly accepts a caller-supplied `deadline`, so this is an inconsistency that exposes outbound swaps to MEV.
- **Impact**: Sandwich attacks and long-lurking MEV on outbound (swapOut) legs; users systematically receive worse execution than the quoted `amountOutMin` would imply when combined with delayed inclusion.

## Approve Race / Wrong Approval Amount in `swapIn`
- **Location**: 
  - `chain/avalanche/src/contracts/AvaxAggregator.sol` : `swapIn`
  - `chain/ethereum/contracts/THORChain_Aggregator.sol` : `swapIn`
- **Mechanism**: Both aggregators approve the *requested* `amount` to the swap router *without first resetting the allowance to 0*, then swap using `safeAmount`/`_safeAmount` (the actually-received balance delta after `safeTransferFrom`). Two problems compound: (a) for strict ERC20s like USDT that revert when `approve` is changed from non-zero to non-zero, this reverts on subsequent calls; (b) when a fee-on-transfer token is used, the leftover allowance (`amount - safeAmount`) stays granted to the swap router indefinitely, and any contract the router is later replaced with (or the same router in another context) could pull that residual.
- **Impact**: Denial-of-service on subsequent swaps of strict tokens (USDT-class) and a standing residual allowance left on the swap router equal to the fee delta — exploitable if the swap router address is ever rotated or compromised.

## Stale / Donated AVAX Counted as Swap Proceeds
- **Location**: `chain/avalanche/src/contracts/AvaxAggregator.sol` : `swapIn`
- **Mechanism**: After `swapExactTokensForAVAX`, the contract reads `safeAmount = address(this).balance` and forwards *the entire* balance to THORChain via `depositWithExpiry`. The contract has a `receive() external payable {}` function, so any AVAX that was previously stranded (a failed prior swap, a direct `send`/`transfer` to the aggregator, or even forced AVAX from `selfdestruct`) is mixed into the outbound deposit. The Ethereum `THORChain_Aggregator.swapIn` has the identical pattern.
- **Impact**: Anyone can inflate the forwarded AVAX amount by force-sending AVAX to the aggregator just before calling `swapIn` (or by exploiting dust from a prior failed swap). Combined with the fact that the THORChain memo is set by `msg.sender`, this lets the caller donate AVAX to a vault they don't control, or, more dangerously, lets a previously-rejected swap's residual AVAX be credited against a *different* inbound memo — corrupting cross-chain settlement accounting.

## Unbounded Loop Arrays in V5 Batch Functions
- **Location**: `chain/ethereum/contracts/THORChain_Router.sol` : `batchTransferOutV5` and `batchTransferOutAndCallV5`
- **Mechanism**: Both functions iterate `transferOutPayload.length` / `aggregationPayloads.length` with no upper bound and no pagination. A caller-supplied vault can submit an arbitrarily large `calldata` array. Because the per-iteration body does an external token `transfer`/`swapOutV5` call (each consuming ≥60k gas plus 2300-gas-griefable `send`), gas can be manipulated. More importantly, `transferOutV5`/`transferOutAndCallV5` are `nonReentrant`, so any revert in iteration N poisons the whole batch with no partial-success semantics — but the lack of a length cap means a malicious vault can grief by submitting arrays sized to push the transaction over the block gas limit, DoS'ing legitimate outbound batches.
- **Impact**: Outbound batch transactions can be DoS'd by an attacker submitting oversized arrays; the bifrost gas-budget comment ("no more than 50% than L1 gas limit") is enforced at a layer above but is not structurally enforced here.

## `safeApprove` Ignores Returndata
- **Location**: `chain/ethereum/contracts/THORChain_Aggregator.sol` : `safeApprove` (used by `swapOutV5` and `swapIn`)
- **Mechanism**: The helper does `(bool success, ) = _asset.call(...)` and only `require(success)`. It does not check the ABI-decoded `bool` return value, unlike `safeTransferFrom` in the same file. Tokens that signal failure by returning `false` rather than reverting (the canonical SafeERC20 pattern, and tokens that wrap approve with extra logic) will appear to succeed but the allowance won't actually be updated.
- **Impact**: Subsequent swap attempts with the (un-approved) token will revert at the DEX level; in `swapIn` this is a user-visible DoS, and in `swapOutV5` the `require(aggSuccess, "swapExactTokensForETH failed")` will trip, but the vault's allowance was already decremented upstream in `transferOutAndCallV5` (see fee-on-transfer finding) — compounding the accounting loss.

## Missing Zero-Address Validation on User/Recipient Parameters
- **Location**: 
  - `chain/avalanche/src/contracts/AvaxAggregator.sol` : `swapIn` (`tcVault`, `tcRouter`, `token`), `swapOut` (`token`, `to`)
  - `chain/ethereum/contracts/THORChain_Aggregator.sol` : `swapIn`, `swapOut`, `swapOutV5` (all `address` parameters)
  - `chain/ethereum/contracts/THORChain_Router.sol` : `transferOut*`, `transferAllowance`, `returnVaultAssets`
- **Mechanism**: None of these functions check that `vault`, `to`, `target`, `finalToken`, or `token` are non-zero. If `to == address(0)` is passed to `swapOut`/`swapOutV5`, the DEX sends the output ERC20 to the zero address (irretrievably burned). If `tcVault == address(0)` is passed to `swapIn`, the AVAX/ETH is sent to a dead address with no recovery.
- **Impact**: Permanent, unrecoverable loss of funds on any caller mistake or malicious parameter injection into the memos the THORChain vault forwards.
