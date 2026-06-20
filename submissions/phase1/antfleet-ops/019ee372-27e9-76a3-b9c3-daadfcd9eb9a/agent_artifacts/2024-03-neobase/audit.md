# Audit: 2024-03-neobase

Here are the security vulnerabilities found in the codebase.

## 1. Governance removing a market completely freezes LiquidityGauge operations and locks user claims
- Location: `LendingLedger.sol` : `whiteListLendingMarket` and `update_market`
- Mechanism: The function `update_market` contains a requirement `require(lendingMarketWhitelist[_market], "Market not whitelisted");`. `update_market` is invoked on virtually every market interaction, including user claims (`claim(address)`) and ledger synchronizations (`sync_ledger` via LiquidityGauges). If governance sets a previously whitelisted market's whitelist status to `false`, any calls to `update_market` for that market will cleanly revert.
- Impact: If a market is removed from the whitelist, all users who have staked their underlying tokens in the associated `LiquidityGauge` will be permanently locked out from withdrawing their deposits. This happens because withdrawing tokens from the gauge triggers `_burn` -> `_afterTokenTransfer` -> `sync_ledger()`, which calls the now-reverting `update_market`. Additionally, any honestly accumulated but unclaimed CANTO rewards in the ledger will become permanently unclaimable for the same reason.

## 2. Incorrect application of current gauge weights to historical checkpointed epochs
- Location: `LendingLedger.sol` : `update_market`
- Mechanism: When updating market rewards, the ledger uses a `while(i < block.number)` loop to step through past epochs block-by-block, ostensibly fetching the corresponding gauge weights for each old epoch. However, as it evaluates each epoch block, it calculates `epochTime` using the *current* `block.number` instead of the historical iteration block `i` or `epoch`:
  `uint256 epochTime = referenceBlockTime + ((block.number - referenceBlockNumber) * averageBlockTime) / 1000;` 
  This fetches the relative gauge weight at the *present block's* approximated timestamp rather than the timestamp of the past epochs being looped through. 
- Impact: Users and attackers can manipulate the voting weight on their target gauge and artificially delay the `update_market()` call. When the market is finally updated, the newly manipulated, currently active voting weights will be recursively applied backwards against all previous skipped epochs. This allows malicious voters to steal excessive inflation rewards by suddenly shifting gauge votes and immediately applying them retroactively to past intervals.
