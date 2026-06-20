# Audit: 2024-03-canto

## Missing Access Control on lzCompose
- Location: contracts/asd/asdRouter.sol : lzCompose
- Mechanism: The function is declared `external payable` with no `onlyEndpoint`, `msg.sender` check against the LayerZero endpoint/executor, or other authorization. Any caller can supply arbitrary `_message`, `_guid`, `_executor`, etc.
- Impact: Attacker can force arbitrary decode paths, trigger `_refundToken` (transferring tokens held by the router), initiate unwanted swaps/deposits, or cause denial-of-service via repeated failed compose handling.

## Unsafe Token Transfers Ignoring Return Values
- Location: contracts/asd/asdRouter.sol : _refundToken
- Mechanism: `IERC20(_tokenAddress).transfer(_refundAddress, _amount)` (and native `payable(_refundAddress).transfer`) are used without checking the `bool` return value or using `SafeERC20.safeTransfer`.
- Impact: Failed transfers (e.g., non-compliant tokens, blacklisted recipients, or reverts) silently succeed from the contract's perspective, leaving tokens stuck in the router instead of reaching the refund address.

## Incorrect Decimal Scaling in ASDUSDC
- Location: contracts/asd/asdUSDC.sol : deposit, withdraw
- Mechanism: `amountToMint = _amount * (10 ** (this.decimals() - ERC20(_usdcVersion).decimals()))` and the reverse division in withdraw perform unchecked arithmetic assuming the USDC version always has fewer decimals than 18. No `decimals()` override exists on ASDUSDC.
- Impact: Whitelisting a token with >18 decimals causes underflow revert on deposit/withdraw; a token with <6 decimals can produce massive over-minting or precision loss, allowing attackers to mint unbounded asdUSDC or drain underlying balances.

## Slippage Check Bypass and Incorrect Flow Direction in Swap
- Location: contracts/asd/asdRouter.sol : _swapOFTForNote
- Mechanism: `calcImpact` result is inspected with `isNoteBase` logic, but the subsequent `swap` call hardcodes `!isNoteBase` for both `isBuy` and `inBaseQty` without re-validating the actual received amount against `minOut` after the call; the decoded `(baseUsed, quoteUsed)` is trusted unconditionally.
- Impact: Attacker can supply a `_minAmountASD` that passes the impact check but results in the swap returning less NOTE than expected (or zero), causing the deposit to fail and NOTE to be refunded to an attacker-controlled address while the original OFT is already consumed.

## Reentrancy via External Call in Deposit Path
- Location: contracts/asd/asdRouter.sol : _depositNoteToASDVault (called from lzCompose)
- Mechanism: `IERC20(noteAddress).approve` is performed, followed by an unbounded `.call` to `ASDOFT.mint` (which itself performs `safeTransferFrom` + Compound `mint`). No reentrancy guard exists around the call.
- Impact: A malicious ASD vault (or compromised cNote) can re-enter during the mint, potentially draining NOTE or ASD tokens from the router before the success/failure handling in lzCompose completes.
