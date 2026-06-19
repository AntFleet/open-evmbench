# Audit: 2024-05-loop

## Non-ETH claims sweep unrelated ETH in the contract
- Location: `src/PrelaunchPoints.sol` : `_claim`
- Mechanism: In the non-ETH claim path, the contract swaps the user’s token amount, then sets `claimedAmount = address(this).balance` and deposits that entire ETH balance into `lpETH` for the claimant. It does not use the ETH delta produced by the swap. Because the contract has a payable `receive()` function, anyone can leave ETH in the contract after `convertAllETH`, and a claimant can also call with `_percentage == 0`, consuming no token balance while still sweeping any residual ETH.
- Impact: A user with any non-ETH balance can claim all stray ETH held by the contract as lpETH, including ETH accidentally sent directly to the contract after conversion. This contradicts the comment that directly sent ETH is “locked forever” and turns residual ETH into a first-claimant windfall.

## Fee-on-transfer allowed tokens create inflated user balances
- Location: `src/PrelaunchPoints.sol` : `_processLock`
- Mechanism: For ERC20 locks, the contract credits `balances[_receiver][_token] += _amount` after calling `safeTransferFrom`, but never checks the actual token balance increase. If an allowed token takes a transfer fee, burns on transfer, or otherwise delivers less than `_amount`, the internal accounting records more tokens than the contract received.
- Impact: The first users to withdraw or claim that token can consume more than their fair share of the contract’s actual token balance, leaving later users undercollateralized or unable to withdraw/claim. This is exploitable for any allowed token with deflationary or fee-on-transfer behavior.

