# Audit: 2024-01-canto

## Block-Timestamp Unit Confusion in Gauge Weight Calculation
- Location: `LendingLedger.sol` : `update_market`
- Mechanism: `LendingLedger` structures its reward epochs based on block numbers (e.g., `(i / BLOCK_EPOCH) * BLOCK_EPOCH`). When updating the market, it calls `gaugeController.gauge_relative_weight_write(_market, epoch)` to scale the rewards, passing the block-based `epoch` as the time parameter. However, `GaugeController.sol` expects `_time` to be a Unix timestamp, heavily relying on time-based calculations like `(_time / WEEK) * WEEK` (where `WEEK = 604800`). Because block numbers (millions) are drastically smaller than current Unix timestamps (~billions), the passed `epoch` evaluates to a date in 1970. 
- Impact: The gauge weight lookup will query deep past state that does not have initialized weights, meaning `gauge_relative_weight_write` will permanently return `0`. Consequently, `cantoReward` evaluates to zero and no CANTO emissions can be distributed to users. 

## De-whitelisting a lending market locks previously earned user rewards
- Location: `LendingLedger.sol` : `claim`
- Mechanism: The `claim` function requires an upfront invocation of `update_market(_market)` to ensure ledger state is fully synchronized. However, `update_market` enforces strict access control: `require(lendingMarketWhitelist[_market], "Market not whitelisted");`. If governance removes a market from the whitelist (typically to sunset a market and stop future emissions), this requirement will subsequently cause every call to `claim` for that market to revert.
- Impact: Users are globally griefed from withdrawing any past accrued CANTO rewards from the de-whitelisted market, leading to permanently unclaimable user funds.

## VotingEscrow user locks can be permanently trapped if delegation was supported
*(Note due to incomplete implementation)*
- Location: `VotingEscrow.sol` : `increaseAmount` / `withdraw`
- Mechanism: The contract retains code allowing for locks to be delegated (`locked_.delegatee`), but misses the `delegate` function itself. If a user lock's `delegatee` were conceptually set to an alternate address, they could never withdraw. The `withdraw` function explicitly has `require(locked_.delegatee == msg.sender, "Lock delegated");`, meaning it strictly prohibits withdrawal while delegated. Because there is no functional `undelegate` feature implemented allowing users to revoke delegation, any delegated lock funds would be frozen forever. 
- Impact: If the missing delegation state change logic was added or bypassed in a deployment variation, affected users' native CANTO deposits would be completely irretrievable upon lock expiration. Since `delegatee` defaults to `msg.sender`, it survives in its current state as dead code.
