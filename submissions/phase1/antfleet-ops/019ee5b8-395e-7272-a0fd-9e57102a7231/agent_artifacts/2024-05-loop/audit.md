# Audit: 2024-05-loop

## Token claims mint lpETH from the entire contract ETH balance
- Location: `src/PrelaunchPoints.sol` : `_claim`
- Mechanism: In the non-ETH claim path, `_fillQuote()` measures the ETH received from the 0x swap but discards that delta. `_claim()` then sets `claimedAmount = address(this).balance` and deposits the entire contract ETH balance into `lpETH` for the claimant. The contract also has an unrestricted payable `receive()`, so ETH can be sent or force-sent without being attributed to any user.
- Impact: Any user with a non-ETH locked balance can claim all stray ETH in the contract as lpETH. With `_percentage` rounding to zero, the attacker can potentially sweep that ETH without reducing their recorded token balance.

## UniswapV3 swap validation reads a fake path
- Location: `src/PrelaunchPoints.sol` : `_decodeUniswapV3Data`
- Mechanism: `sellTokenForEthToUniswapV3(bytes,uint256,uint256,address)` uses an ABI offset for the dynamic `encodedPath`, but `_decodeUniswapV3Data()` ignores that offset and hard-codes where the path should be. A caller can place a valid-looking fake path where the validator reads, while the 0x proxy decodes and executes a different path from the real ABI offset.
- Impact: The contract’s check that the swap is `_token -> WETH/ETH` can be bypassed for UniswapV3 calldata. A claimant can make the contract execute an unvalidated swap route after the contract approves the 0x proxy, breaking the intended protection around user-supplied swap data.

## Token deposits over-credit fee-on-transfer or deflationary tokens
- Location: `src/PrelaunchPoints.sol` : `_processLock`
- Mechanism: For non-WETH ERC20 deposits, the contract credits `balances[_receiver][_token] += _amount` after `safeTransferFrom()` without measuring the actual token balance delta received by the contract. If an allowed token takes a transfer fee or otherwise delivers less than `_amount`, internal balances exceed real reserves.
- Impact: Recorded user claims/withdrawals can exceed the contract’s actual token holdings. Early withdrawers or claimers can consume more than their net contribution, leaving later users unable to withdraw or claim their recorded balances.

