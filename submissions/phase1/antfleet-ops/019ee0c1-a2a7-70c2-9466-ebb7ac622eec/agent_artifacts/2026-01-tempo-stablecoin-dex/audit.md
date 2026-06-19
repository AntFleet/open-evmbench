# Audit: 2026-01-tempo-stablecoin-dex

## Unchecked emergency withdrawal lets anyone drain reserves
- Location: `contracts/StablecoinDEX.sol` : `emergencyWithdraw` / `_processWithdrawal`
- Mechanism: `emergencyWithdraw` is external and performs no balance, authorization, token, or amount checks before calling `_processWithdrawal`. `_processWithdrawal` subtracts `balances[user][token]` and `totalDeposits[token]` inside `unchecked`, so a caller with zero balance can underflow their internal balance and then receive `amount` tokens from the DEX.
- Impact: Any attacker can call `emergencyWithdraw(token, amount)` for any token held by the contract and withdraw up to the contract’s actual token balance, draining other users’ deposited and locked funds.

## Anyone can cancel any maker’s order
- Location: `contracts/StablecoinDEX.sol` : `cancel`
- Mechanism: `cancel` loads the order and calls `_cancelOrder` without checking `msg.sender == order.maker`. The declared `Unauthorized` error is never used. `_cancelOrder` unlinks the order and refunds the remaining locked base tokens to the maker.
- Impact: Any account can cancel any open order. Attackers can grief makers, remove liquidity from the book, disrupt routing/settlement flows, and force market makers out of positions even though they cannot steal the refunded funds.

## Deposits credit requested amount instead of received amount
- Location: `contracts/StablecoinDEX.sol` : `deposit`
- Mechanism: `deposit` credits `balances[msg.sender][token] += amount` after `safeTransferFrom`, but never verifies the contract’s actual balance delta. Fee-on-transfer, deflationary, rebasing, policy-taxed, or otherwise non-standard tokens can transfer less than `amount` while the DEX credits the full amount internally.
- Impact: The DEX can become insolvent for that token. An attacker can over-credit themselves by depositing a token that delivers less than requested, then withdraw or trade against honest users’ real deposited liquidity of the same token.

## Stablecoin price bound is declared but not enforced
- Location: `contracts/StablecoinDEX.sol` : `placeOrder`
- Mechanism: The contract defines `MAX_PRICE_DEVIATION` as a 1% stablecoin parity bound, but `placeOrder` only rejects `price == 0`. Orders with arbitrary prices can be inserted into the orderbook, including as the head order.
- Impact: Makers can publish extreme mispriced stablecoin orders despite the documented invariant. Any taker, settlement agent, or routing integration that relies on the DEX enforcing stablecoin price bounds can be made to execute swaps at abusive prices.

