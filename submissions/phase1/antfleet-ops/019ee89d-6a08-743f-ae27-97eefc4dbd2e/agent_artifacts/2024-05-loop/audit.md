# Audit: 2024-05-loop

## UniswapV3 swap validation can be bypassed via a non-canonical calldata offset
- Location: src/PrelaunchPoints.sol : `_validateData` / `_decodeUniswapV3Data`
- Mechanism: `_decodeUniswapV3Data` reads the Uniswap `encodedPath` from hard-coded calldata positions (length at `_data.offset+132`, first token at `+164`, last token at `+164+len-20`) instead of following the ABI offset pointer that the real `sellTokenForEthToUniswapV3(bytes,uint256,uint256,address)` decoder uses. The dynamic-argument head word at calldata offset `4` — which points 0x's decoder to where the path actually lives — is never read or validated to equal `0x80`. An attacker can therefore embed two different paths in `_data`: a canonical decoy at offset 132 that makes `_validateData` observe `inputToken == _token` and `outputToken == WETH`, and a real path placed elsewhere and referenced by the unvalidated offset pointer, which is the one the 0x exchange proxy actually decodes and executes in `_fillQuote`. The swap that is validated is not the swap that is executed; only `sellAmount` and `recipient` (which are static head fields read at the same offsets by both) are genuinely pinned.
- Impact: Combined with the standing allowance below, an attacker can direct the proxy to swap a different pooled token out of the contract than the one debited from their own `balances`, draining other depositors' locked tokens.

## ERC20 allowance to the exchange proxy is never reset after a swap
- Location: src/PrelaunchPoints.sol : `_fillQuote`
- Mechanism: `_fillQuote` calls `require(_sellToken.approve(exchangeProxy, _amount))` before the call but never zeroes the allowance afterward. When a swap consumes less than `_amount` (e.g. a partially-filled order routed through `transformERC20`, whose `transformations` array is entirely attacker-controlled and unvalidated), a residual allowance for that token to the exchange proxy persists across subsequent calls. This standing allowance is the precondition that converts the offset-validation gap above into theft: a later, offset-manipulated UniswapV3 claim can make the proxy pull the still-approved token Z out of the shared pool while the caller's `balances[msg.sender][_token]` is only debited for an unrelated `_token`.
- Impact: Residual approvals let a follow-up swap pull a pooled token the caller never debited, enabling extraction of other depositors' funds and leaving the pool's tokens approved to an external contract beyond the single intended swap.

## Fee-on-transfer / deflationary tokens are over-credited on lock
- Location: src/PrelaunchPoints.sol : `_processLock`
- Mechanism: For the ERC20 branch, `_processLock` does `IERC20(_token).safeTransferFrom(msg.sender, address(this), _amount)` and then credits `balances[_receiver][_token] += _amount`, using the requested amount rather than the actual received balance delta. Any allow-listed token that deducts a transfer fee (or otherwise delivers less than `_amount`) causes the contract to record more than it custodies. The shared pool then owes more of that token than it holds, and `_claim`/`withdraw` for earlier depositors drains the shortfall from later ones; the contract only guards against rebasing tokens, not fee-on-transfer behavior.
- Impact: If such a token is ever allow-listed via `allowToken`, depositors are over-credited and the final claimers/withdrawers cannot be made whole, producing protocol insolvency for that token.

## Token claim captures stray ETH sent to the contract
- Location: src/PrelaunchPoints.sol : `_claim` (non-ETH branch)
- Mechanism: After the token→ETH swap, `_claim` sets `claimedAmount = address(this).balance` — the entire contract balance — rather than the swap delta that `_fillQuote` actually measures (`boughtETHAmount`, which is computed but discarded into an event). Because `receive()` accepts arbitrary ETH (documented as "locked forever") and any rounding/donated ETH accumulates with no other owner, the whole balance is swept and minted 1:1 as lpETH to whoever performs the next token claim.
- Impact: ETH sent directly to the contract is not locked but is silently captured by the next token-claiming user, who receives lpETH for value they never contributed.

