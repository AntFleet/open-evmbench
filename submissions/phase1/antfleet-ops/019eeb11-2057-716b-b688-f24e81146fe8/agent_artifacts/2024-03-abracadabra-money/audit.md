# Audit: 2024-03-abracadabra-money
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## LP oracle always reports a price of zero (missing return in `_getReserves`)
*(consensus, 6 of 6 reports)*
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `_getReserves` / `latestAnswer`
- Mechanism: `_getReserves()` is declared `returns (uint256, uint256)` but its body assigns `pair.getReserves()` only to local variables and falls off the end with no `return`, so it silently returns the zero-defaults `(0, 0)`. `latestAnswer()` then computes `int256(minAnswer * (baseReserve + quoteReserve) / pair.totalSupply())` with both reserves `0`, yielding a price of exactly `0` regardless of real pool balances (and a division-by-zero revert when `totalSupply()` is `0`). Contract compiles (unused-variable warning only).
- Impact: Every market that prices a MagicLP token through this aggregator reads collateral value as `0`. Depending on the downstream adapter this is critical in either direction: a direct feed makes `_isSolvent` evaluate borrow side to `0`, enabling unlimited borrowing against worthless collateral **or** instant mass-liquidation/theft of all LP-collateralized positions; an inverting adapter (`1 / answer`) reverts on divide-by-zero, bricking borrow/liquidation. Wrong on the first read from deployment; no attacker setup required.

## Fee setter validates the wrong variable, allowing fees ≥ 100%
*(consensus, 5 of 6 reports)*
- Location: `src/mixins/FeeCollectable.sol` : `setFeeParameters` (with `calculateFees`)
- Mechanism: The bounds check reads the current storage value `feeBips` instead of the incoming `_feeBips` (`if (feeBips > BIPS)` should be `if (_feeBips > BIPS)`). Since `feeBips` starts at `0`, the guard never fires, and an authorized fee operator can store any `uint16` up to 65535 (≈655%) into `feeBips`, unvalidated. `calculateFees` then computes `feeAmount = amountIn * feeBips / BIPS > amountIn`, so `userAmount = amountIn - feeAmount` underflows and reverts (checked 0.8 math), DoSing every fee-taking path; at exactly 100% it silently routes all input to the fee collector. One report additionally notes a *permanent brick*: once `feeBips > BIPS` is stored, the guard `feeBips > BIPS` reverts on every subsequent call, so the value can never be corrected.
- Impact: A single privileged fee-operator role can set an out-of-range fee that confiscates 100% of `amountIn` or reverts all fee math, potentially irreversibly, for any contract inheriting this mixin.
- Reviewer disagreement (if any): One report flags this as a *latent* defect — the mixin is currently only `import`ed in `script/Blast.s.sol` and not inherited by any deployed contract in this set — so it considers it not presently exploitable but still a bug to fix.

## Aggregator's own `latestRoundData` returns hardcoded zero timestamps (feed appears permanently stale)
*(consensus, 3 of 6 reports)*
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `latestRoundData`
- Mechanism: `latestRoundData()` returns `updatedAt = 0` and `roundId = 0` (hardcoded zero timestamps and round IDs).
- Impact: Any consumer that performs a staleness/freshness check on this feed treats it as permanently stale, which can block updates or cause the consumer to reject/mishandle the feed.

## Underlying oracle answers consumed without freshness or sign checks
*(consensus, 2 of 6 reports)*
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `latestAnswer`
- Mechanism: `latestAnswer()` reads `baseOracle.latestAnswer()` / `quoteOracle.latestAnswer()` directly and casts each `int256` to `uint256`, with no checks for `answer <= 0`, stale rounds, incomplete rounds, `answeredInRound`, or `updatedAt`. A stale answer is treated as current, and a negative answer becomes a huge unsigned value after the cast.
- Impact: If either underlying feed is stale, incomplete, or returns a negative value, the LP token is materially mispriced. A borrower or liquidator can exploit inflated/stale collateral valuation in any downstream market (e.g., borrow against inflated collateral and leave bad debt).

## Cauldron falls back to a stale cached exchange rate on failed oracle updates
*(consensus, 2 of 6 reports)*
- Location: `src/cauldrons/CauldronV4.sol` : `updateExchangeRate` (used by `borrow`, `removeCollateral`, `cook`, `liquidate`)
- Mechanism: When `oracle.get(oracleData)` returns `updated == false`, `updateExchangeRate()` silently returns the previously cached `exchangeRate` with no freshness bound. Solvency checks and liquidations then proceed using that old rate.
- Impact: If the oracle stops updating (or can be made to return `false`) while the real collateral price has moved, borrowers can overborrow or remove collateral against a stale favorable rate; stale unfavorable rates can enable incorrect liquidations or block legitimate ones.
- Reviewer disagreement (if any): Three reports reviewed CauldronV4 and defended it as matching the known-good canonical V4 (`accrue`/`_borrow`/`_repay`/`liquidate`/`_isSolvent`/`cook`), implicitly treating the cached-rate fallback as intended canonical behavior.

## Onboarding LP shares allocated by raw token amounts instead of value
*(consensus, 2 of 6 reports)*
- Location: `src/blast/BlastOnboardingBoot.sol` : `_claimable`
- Mechanism: `_claimable()` computes a user's LP share as `(locked MIM + locked USDB) / (total locked MIM + total locked USDB)`, treating one MIM and one USDB as identical units. It does not normalize the two assets by the bootstrap price (the pool uses `I = 0.998 ether`) or any market/oracle price, even though bootstrap liquidity is created at a fixed MIM/USDB price.
- Impact: A user can lock the cheaper/underpriced side and receive the same proportional LP allocation as users who locked the more valuable side, diluting honest participants and extracting value after `claim()`; severity grows as MIM/USDB pricing diverges or one side depegs.
- Reviewer disagreement (if any): Two reports defended this code path, arguing `_claimable` is `floor(userLocked * shares / totalLocked)` so the per-user sum can never exceed `totalPoolShares` (a defense addressing over-allocation of total shares, not the value-weighting concern).

## Minority findings

## Expired staking locks keep earning boosted rewards until an operator processes them
*(minority, 1 of 6 reports)* *(conflicting reviews: 3 of 6 reports defended this code path)*
- Location: `src/staking/LockingMultiRewards.sol` : `balanceOf`, `totalSupply`, `getRewards`, `processExpiredLocks`
- Mechanism: Reward accounting uses `_balances[user].locked` and `lockedSupply` for boosted weight without checking each lock's `unlockTime`. Expired locks are only converted back to unlocked balances by `processExpiredLocks()`, which is operator-only.
- Impact: A user whose lock has expired can keep claiming rewards at the boosted locked weight until an operator includes them in processing, diluting active stakers. Preconditions: the lock is expired and operator processing is delayed, censored, or unavailable.
- Reviewer disagreement (if any): Three reports examined LockingMultiRewards and defended it as internally consistent — rewards updated before every balance/supply mutation (including `processExpiredLocks`), consistent boosted `totalSupply`/`balanceOf`, and a 13-week lock that prevents short-term boost gaming.

