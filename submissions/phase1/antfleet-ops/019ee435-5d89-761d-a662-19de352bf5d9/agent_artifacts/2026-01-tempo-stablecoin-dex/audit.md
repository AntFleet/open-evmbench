# Audit: 2026-01-tempo-stablecoin-dex

## Unauthenticated emergency withdrawal drains escrowed funds
- Location: `contracts/StablecoinDEX.sol` : `emergencyWithdraw`
- Mechanism: `emergencyWithdraw()` calls `_processWithdrawal()` without checking that `balances[msg.sender][token] >= amount`. `_processWithdrawal()` then subtracts inside `unchecked`, so an attacker with zero balance can underflow their internal balance and `totalDeposits[token]`, then receive real tokens via `safeTransfer`.
- Impact: Any attacker can withdraw any token held by the DEX, up to the contract’s token balance per call, draining user deposits and locked order liquidity.

## Anyone can cancel any maker’s order
- Location: `contracts/StablecoinDEX.sol` : `cancel`
- Mechanism: `cancel()` only checks that `order.maker != address(0)` and never requires `msg.sender == order.maker`. It then calls `_cancelOrder()`, which unlinks the order and refunds the remaining locked base tokens to the maker.
- Impact: Any address can forcibly remove any open order from the orderbook. Attackers cannot steal funds through this path, but they can censor liquidity, grief market makers, and disrupt routing/matching by cancelling quotes at will.

## Partial fills can underpay makers through rounding
- Location: `contracts/StablecoinDEX.sol` : `fillOrder`
- Mechanism: `quoteAmount` is computed as `(amount * price) / 1e18`, which rounds down. Because `fillOrder()` allows arbitrarily small partial fills, a taker can split one fill into many tiny fills and receive the same total base amount while repeatedly benefiting from truncation.
- Impact: Makers can receive less quote token than their limit price implies. For example, at `price = 1.01e18`, filling `1e6` base units at once costs `1,010,000` quote units, but filling one unit at a time costs only `1,000,000`, extracting the full 1% price premium from the maker.

