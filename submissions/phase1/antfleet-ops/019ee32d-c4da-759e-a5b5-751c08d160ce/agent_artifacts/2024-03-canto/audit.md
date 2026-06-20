# Audit: 2024-03-canto

## OFT Bridging Allows Owner to Drain User Backing Principal as Carry (Insolvency)
- Location: `contracts/asd/asdOFT.sol` : `withdrawCarry`
- Mechanism: `ASDOFT` implements LayerZero v2's `OFT` standard, where bridging tokens out of Canto burns them locally via `_burn`, decreasing the Canto contract's local `totalSupply()`. Crucially, the backing `cNOTE` collateral in the contract is not modified during bridging. The `withdrawCarry` function calculates the maximal withdrawable carry as `balanceOfUnderlying(address(this)) - totalSupply()`. Because the local `totalSupply()` decreases while the contract's `cNOTE` balance remains the same, the contract incorrectly classifies the principal collateral of bridged-out tokens as surplus interest (carry). The owner can withdraw this backing principal. 
- Impact: The contract owner can withdraw the main NOTE backing of all currently bridged-out tokens. When those users bridge their tokens back to Canto (which mints them back and increases `totalSupply()`), the contract will be highly under-collateralized/insolvent, and users will be unable to burn their `asD` for native `NOTE`, resulting in a permanent loss of user funds.

## Missing Access Control on `lzCompose` in `ASDRouter`
- Location: `contracts/asd/asdRouter.sol` : `lzCompose`
- Mechanism: The `lzCompose` function is designed to be called only by the LayerZero Endpoint to execute cross-chain composed messages. However, `ASDRouter` contains no validation (no `msg.sender == endpoint` check) and does not store the endpoint address to enforce access control. Consequently, any external address can call `lzCompose` directly with arbitrary arguments.
- Impact: An attacker can call `lzCompose` directly and pass a custom-fabricated `_message` with their own address as the receiver. If there are any idle or unprocessed tokens (such as USDC or NOTE from a failed transaction or direct transfers) sitting in the `ASDRouter` contract, the attacker can sweep these funds entirely to themselves.

## Denial of Service via `transfer()` to Reverting Refund Address in `_refundToken`
- Location: `contracts/asd/asdRouter.sol` : `_refundToken`
- Mechanism: During execution failures (such as a swap slippage failure or deposit failure), `lzCompose` handles errors by calling `_refundToken` to return native and ERC20 tokens back to the user's refund address (`_payload._cantoRefundAddress` or `composeFrom`). To return native tokens (the native gas provided by the executor), the function uses the Solidity primitive `payable(_refundAddress).transfer(_nativeAmount)`. If the user-provided refund address is a contract that lacks a `receive()` or `fallback()` function, or if it reverts upon receiving native tokens, the `transfer()` call will throw an untamed revert.
- Impact: Any failure handling that attempts to refund native tokens to an incompatible contract will revert the entire transaction. In LayerZero v2, the executor will get permanently blocked because `lzCompose` must never revert, causing a complete denial of service (DoS) for the cross-chain messaging channel.

## Revert of `withdrawCarry` due to `STATICCALL` on State-Mutating `balanceOfUnderlying`
- Location: `contracts/asd/asdOFT.sol` : `withdrawCarry`
- Mechanism: The contract declares `balanceOfUnderlying` as a `view` function in `CTokenInterface`. In Solidity version `^0.8.22`, calling functions declared as `view` via an interface compiles down to an EVM `STATICCALL`. However, in Compound V2 / Canto forks, the actual `balanceOfUnderlying` implementation on the `cToken` contract is state-mutating because it triggers block-by-block interest accrual (`accrueInterest()`) which writes to storage. The EVM will immediately revert any transaction that attempts to modify storage during a `STATICCALL`.
- Impact: The `withdrawCarry` function will always revert whenever it is called. The owner is permanently blocked from withdrawing any legitimate carry interest earned by the protocol.

## Incorrect Price Limit (`limitPrice = 0`) in CrocSwap (Ambient) will Cause Swaps to Always Revert
- Location: `contracts/asd/asdRouter.sol` : `_swapOFTForNote`
- Mechanism: In `_swapOFTForNote`, a swap is executed on Ambient (CrocSwap) by calling `ICrocSwapDex.swap` with `limitPrice` hardcoded to `0`. In CrocSwap, `limitPrice` represents the boundary price (in Q64.96 sqrt price) at which the swap must stop. If `isBuy` is true (buying `$NOTE`), the price will rise during execution, and passing `limitPrice = 0` means the maximum price we are willing to accept is `0`. Since any active pool has a price higher than `0`, this is treated as a breach of the price limit, and CrocSwap will instantly revert.
- Impact: For swaps where `isBuy` is true (which occurs when `_oftAddress` is lower than `noteAddress`), the transaction will always revert. This renders the bridge completely inoperable in that direction, forcing all transactions to fail and activate the error-prone refund path.
