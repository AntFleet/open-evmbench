# Audit: 2024-03-canto

## Missing origin verification on lzCompose allows theft of pending compose tokens
- Location: contracts/asd/asdRouter.sol : lzCompose
- Mechanism: `lzCompose` is public and performs no verification that the caller is the LayerZero executor or that `_from`/`_guid`/`_message` correspond to a genuine, authenticated LayerZero delivery. Tokens delivered by a real OFT send are credited to this contract *before* `lzCompose` runs; the compose call merely decides what to do with them. Anyone can front-run the legitimate executor call with a forged `_message` whose `OftComposeMessage` points `_cantoRefundAddress` at the attacker, while setting `_minAmountASD` to `type(uint).max` so `_swapOFTForNote` returns `(0, false)`. The router then calls `_refundToken(... asdUSDC, attacker, amountUSDC ...)`, handing the attacker the asdUSDC minted from the victim's deposited USDC.OFT, which can be withdrawn for USDC.
- Impact: Complete theft of any cross-chain USDC.OFT compose delivery that is pending in the router, simply by front-running the executor's `lzCompose` transaction. All user funds routed through this router are at risk.

## Native `.transfer` in refund path can revert the whole compose and lock funds
- Location: contracts/asd/asdRouter.sol : _refundToken
- Mechanism: `_refundToken` uses `payable(_refundAddress).transfer(_nativeAmount)`, which forwards only 2300 gas. If `_refundAddress` is a contract whose receive logic requires more gas, the call reverts. The code comments state `lzCompose` "cannot revert anywhere," yet this refund path is reached on every failure branch and a revert here propagates out of `lzCompose`, aborting the entire handling of a delivery.
- Impact: Compose deliveries whose refund/fee-return address is a contract with non-trivial receive logic become unprocessable; tokens stuck in the router (and any native fee) cannot be recovered through this path, contradicting the design invariant that tokens must always reach the intended receiver.

## Same-chain ASD transfer in _sendASD can revert and abort lzCompose
- Location: contracts/asd/asdRouter.sol : _sendASD
- Mechanism: When `_payload._dstLzEid == cantoLzEID`, `_sendASD` directly executes `ASDOFT(_payload._cantoAsdAddress).transfer(_payload._dstReceiver, _amount)` with no try/catch and no SafeERC20. If the ASD transfer fails (e.g., `_cantoAsdAddress` is not a valid ASD contract, or the router holds fewer ASD tokens than `_amount`), the call reverts and propagates out of `lzCompose`.
- Impact: A single failing transfer at the end of an otherwise-successful compose reverts the entire delivery, stranding the user's funds; this again violates the "cannot revert" invariant the contract relies on for safety.

## recover() bypasses whitelist and mints asdUSDC for arbitrary tokens
- Location: contracts/asd/asdUSDC.sol : recover
- Mechanism: `recover` is owner-only but does not check `whitelistedUSDCVersions[_usdcVersion]`. It reads `ERC20(_usdcVersion).balanceOf`/`decimals()`, credits `usdcBalances[_usdcVersion]`, and mints asdUSDC to the owner for any token passed in. Unlike `deposit`, there is no whitelist gate, and a non-ERC20-compliant or rebasing address could be supplied.
- Impact: Owner can mint asdUSDC against arbitrary/non-whitelisted tokens (or tokens that don't behave like USDC), diluting asdUSDC backing; combined with decimal assumptions that may revert or mis-mint, accounting integrity of asdUSDC can be broken by a compromised or careless owner.

## withdraw() truncation silently burns asdUSDC for zero USDC
- Location: contracts/asd/asdUSDC.sol : withdraw
- Mechanism: For a 6-decimal USDC, `amountToWithdraw = _amount / 10**(18-6)` truncates to 0 for any `_amount < 1e12`, yet `_burn(msg.sender, _amount)` still burns the full asdUSDC amount before transferring 0 USDC. The balance check `usdcBalances >= 0` passes trivially.
- Impact: A user (or an integration calling `withdraw` with a dust amount) irreversibly loses asdUSDC with no USDC returned; accounting divergence between burned asdUSDC and released USDC.
