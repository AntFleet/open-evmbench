# Audit: 2026-01-tempo-stablecoin-dex

## Unchecked emergency withdrawal drains liquidity
- Location: `contracts/StablecoinDEX.sol` : `emergencyWithdraw`, `_processWithdrawal`
- Mechanism: `emergencyWithdraw` is public and calls `_processWithdrawal` without checking the caller’s deposited balance. `_processWithdrawal` then subtracts `balances[user][token]` and `totalDeposits[token]` inside `unchecked`, so a caller with zero balance can underflow their internal balance and still receive tokens if the DEX holds enough of that token.
- Impact: An attacker can withdraw deposited tokens belonging to other users. After one successful underflow, the attacker can retain a huge internal balance and continue draining current or future liquidity for that token.

## Anyone can cancel any order
- Location: `contracts/StablecoinDEX.sol` : `cancel`
- Mechanism: `cancel` only checks that `order.maker != address(0)` and never requires `msg.sender == order.maker`. It then calls `_cancelOrder`, unlinking the order and refunding the maker.
- Impact: Any attacker can remove other users’ open orders from the book, griefing market makers and disrupting available DEX liquidity. Funds are refunded to the maker, but order availability can be censored by any account.

## Dust partial fills underpay makers
- Location: `contracts/StablecoinDEX.sol` : `fillOrder`
- Mechanism: `quoteAmount` is calculated with floor division: `(amount * price) / 1e18`. Since `fillOrder` allows any nonzero fill amount, takers can split fills into dust-sized chunks and lose rounding dust on every fill. For example, at `price = 0.99e18`, filling `amount = 2` charges only `1` quote unit instead of `1.98`.
- Impact: A taker can buy a maker’s base tokens for materially less than the posted price by repeatedly using tiny partial fills, extracting value from makers.

## Deposits over-credit fee-on-transfer or non-standard tokens
- Location: `contracts/StablecoinDEX.sol` : `deposit`
- Mechanism: `deposit` credits `balances[msg.sender][token] += amount` after `safeTransferFrom`, but it never verifies how many tokens the contract actually received. Fee-on-transfer, deflationary, rebasing, or malicious ERC20-compatible tokens can transfer less than `amount` while still returning success.
- Impact: Internal balances can exceed real token reserves. An attacker can use over-credited balances to withdraw other users’ same-token liquidity or trade with unbacked balances, leaving counterparties unable to withdraw the tokens they are credited with.

