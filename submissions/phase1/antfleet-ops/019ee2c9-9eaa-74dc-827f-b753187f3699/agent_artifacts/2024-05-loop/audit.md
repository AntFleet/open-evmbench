# Audit: 2024-05-loop

## LRT claim path can steal any ETH already sitting in the contract
- Location: [PrelaunchPoints.sol](/Users/augstar/open-evmbench/audit_sources/2024-05-loop/src/PrelaunchPoints.sol:253) : `_claim`
- Mechanism: In the non-ETH branch, the contract swaps `userClaim` tokens via `_fillQuote()`, but then ignores the measured swap delta and sets `claimedAmount = address(this).balance` before minting lpETH ([`_fillQuote`]( /Users/augstar/open-evmbench/audit_sources/2024-05-loop/src/PrelaunchPoints.sol:491), [`receive()`]( /Users/augstar/open-evmbench/audit_sources/2024-05-loop/src/PrelaunchPoints.sol:392 )). That means any ETH already present on the contract from direct transfers, forced ETH sends, dust, or any other unexpected source is bundled into the current claimer’s payout. The comment on `receive()` says such ETH is “locked forever”, but `_claim` actually hands it to the next non-ETH claimer.
- Impact: Any account with a non-ETH position can capture arbitrary ETH that lands in the contract after claims open by converting it into lpETH for itself. Accidental ETH transfers and forced ETH sends are therefore stealable, not locked.

## Allowed-token accounting is broken for fee-on-transfer / deflationary / rebasing assets
- Location: [PrelaunchPoints.sol](/Users/augstar/open-evmbench/audit_sources/2024-05-loop/src/PrelaunchPoints.sol:172) : `_processLock`
- Mechanism: `_processLock` credits `balances[_receiver][_token] += _amount` immediately after `safeTransferFrom`, but never measures how many tokens the contract actually received. Later, `withdraw()` and `_claim()` let the user withdraw or swap the full recorded balance ([`withdraw`]( /Users/augstar/open-evmbench/audit_sources/2024-05-loop/src/PrelaunchPoints.sol:274), [`_claim`]( /Users/augstar/open-evmbench/audit_sources/2024-05-loop/src/PrelaunchPoints.sol:240 )). `allowToken()` is only a boolean whitelist and does not enforce the stated “wrapped LRT only / no rebase” assumption. So if any allowed token burns on transfer, charges fees, or rebases downward, internal accounting exceeds real holdings.
- Impact: A depositor of such a token can be over-credited and then exit against later users’ liquidity, or leave the pool undercollateralized so later claim/withdraw calls revert. In practice, early users can drain value and late users eat the deficit.

I did not count the repo’s explicit trusted-owner assumptions or user-chosen slippage/0x-calldata quality issues as vulnerabilities here.

