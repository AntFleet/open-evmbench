# Audit: 2024-08-wildcat

## Protocol fee update push reverts on any single market failure

- Location: `src/HooksFactory.sol` : `pushProtocolFeeBipsUpdates`
- Mechanism: The function iterates over all markets belonging to a hooks template and calls `setProtocolFeeBips` on each via a low‑level `call`. If the call to any market fails (e.g. because that market is closed, or its hooks contract reverts on `onSetProtocolFeeBips`), the entire transaction reverts. This stops the update for the remaining markets.
- Impact: A borrower can block protocol fee updates for all markets that share the same hooks template by closing one of their own markets or by deploying a hooks contract that deliberately reverts on `onSetProtocolFeeBips`. The arch‑controller owner would be unable to update the protocol fee on any market in that template without first removing the problematic market (which only the owner can do) or manually skipping the failing market via the range parameters. This constitutes a denial‑of‑service against the protocol fee update mechanism.
