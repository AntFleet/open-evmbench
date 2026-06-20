# Audit: 2024-08-wildcat

 ## Push-protocol-fee update DoS from closed or already-updated markets
- Location: `src/HooksFactory.sol` : `pushProtocolFeeBipsUpdates(address,uint256,uint256)` and `src/market/WildcatMarketConfig.sol` : `setProtocolFeeBips`
- Mechanism: `pushProtocolFeeBipsUpdates` iterates over `_marketsByHooksTemplate[hooksTemplate]` and calls each market’s `setProtocolFeeBips` with raw `call`; if any call reverts, the whole push reverts. `setProtocolFeeBips` reverts when the market is closed (`ProtocolFeeChangeOnClosedMarket`) and when the new value equals the current value (`ProtocolFeeNotChanged`). Closed markets are never removed from `_marketsByHooksTemplate`, so the blanket push will permanently fail once any market in the list is closed or has already received the update.
- Impact: A borrower can disable future protocol-fee updates for every market that shares a hooks template simply by closing one of their markets. The protocol is forced to fall back to manual, index-by-index updates.

## Disabled hooks template can still be used via existing instances
- Location: `src/HooksFactory.sol` : `_deployMarket` (called by `deployMarket`)
- Mechanism: `deployMarket` resolves the hooks instance to a template and passes the
