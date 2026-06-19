# Audit: 2024-03-abracadabra-money

## MagicLP TWAP can be retroactively manipulated
- Location: `src/mimswap/MagicLP.sol` : `_setReserve`, `_resetTargetAndReserve`, `_sync`, `_twapUpdate`
- Mechanism: Reserve-changing functions write the new reserves first and call `_twapUpdate()` afterward. `_twapUpdate()` then applies `getMidPrice() * timeElapsed` using the already-manipulated reserves for the entire elapsed period since the last update, instead of accumulating the old price before mutation.
- Impact: An attacker can move pool reserves immediately before a TWAP consumer reads `_BASE_PRICE_CUMULATIVE_LAST_`, making the manipulated price count for the whole previous interval and causing any TWAP-based integration to trade, lend, or liquidate at an attacker-chosen price.

## Initial MagicLP rounding can break the configured `I` ratio
- Location: `src/mimswap/MagicLP.sol` : `buyShares`
- Mechanism: Initial share minting checks `quoteBalance < DecimalMath.mulFloor(baseBalance, _I_)`. Because `mulFloor` rounds down, small quote balances can pass the check even when they are insufficient at the intended `I` ratio. The function then sets `_BASE_TARGET_ = shares` and `_QUOTE_TARGET_ = mulFloor(shares, _I_)`, amplifying the rounding error into corrupted PMM targets.
- Impact: An attacker can create a factory-listed pool whose effective pricing ratio differs materially from its advertised `I`, causing later traders to receive malicious prices and lose funds.

## Imbalanced bootstrap liquidity creates exploitable MagicLP targets
- Location: `src/blast/BlastOnboardingBoot.sol` : `bootstrap`; `src/mimswap/periphery/Router.sol` : `createPool`; `src/mimswap/MagicLP.sol` : `buyShares`
- Mechanism: `bootstrap()` passes all locked MIM and USDB into `router.createPool()`. `MagicLP.buyShares()` mints initial shares from the limiting side, but reserves include all tokens sent. If locked MIM and USDB are not in the exact pool ratio, the pool starts with reserves far from the targets while `_RState_` is still initialized as `ONE`, so PMM pricing uses inconsistent reserve/target state.
- Impact: Attackers can trade against the misconfigured initial pool state to extract value from the bootstrapped liquidity, causing losses to users whose locked onboarding deposits funded the pool.

## LP oracle always returns zero reserves
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `_getReserves`, `latestAnswer`
- Mechanism: `_getReserves()` declares a return tuple but only assigns `pair.getReserves()` to local variables and never returns them. `latestAnswer()` therefore receives `(0, 0)` and computes the LP token price from zero reserves.
- Impact: Any market using this aggregator as LP collateral pricing receives a broken price. Depending on the downstream adapter, this can brick borrowing/liquidation flows, mark all LP collateral worthless, or make solvency checks meaningless.

## LP oracle uses manipulable spot reserves
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `latestAnswer`
- Mechanism: The LP price formula values the token from the pool’s current reserves and `totalSupply()`. Those reserves can be changed inside the same transaction with swaps or flash-loaned balances, and there is no comparison against the pool mid-price, invariant-derived fair reserves, or oracle prices.
- Impact: If the reserve-return bug is fixed, an attacker can flash-manipulate reserves to inflate or deflate the LP price, then borrow against overvalued collateral or trigger unfair liquidations.

## Underlying oracle answers are accepted without validity checks
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `latestAnswer`, `latestRoundData`
- Mechanism: The aggregator reads `baseOracle.latestAnswer()` and `quoteOracle.latestAnswer()` directly, casts them to `uint256`, and never checks freshness, round completion, or positive answers via `latestRoundData()`. Its own `latestRoundData()` also returns zero timestamps and round ids.
- Impact: Stale, invalid, or negative underlying feed answers can produce bad LP prices or break downstream oracle consumers, enabling incorrect borrowing and liquidation decisions.

## Fee cap check validates the old fee instead of the new fee
- Location: `src/mixins/FeeCollectable.sol` : `setFeeParameters`
- Mechanism: The function checks `if (feeBips > BIPS)` instead of checking `_feeBips`. When the current stored fee is valid, any new `_feeBips` up to `uint16` max can be set.
- Impact: A permitted fee operator can set fees above 100%. Any concrete inheritor using `calculateFees()` can then revert from underflow, fully tax users, or DoS fee-charging flows.

## Onboarding claims value MIM and USDB as 1:1 despite pool price
- Location: `src/blast/BlastOnboardingBoot.sol` : `_claimable`
- Mechanism: `_claimable()` distributes LP shares using `balances[user][MIM].locked + balances[user][USDB].locked` over total locked MIM plus USDB. The bootstrapped pool is explicitly initialized with `I = 0.998`, so the two tokens are not valued exactly 1:1 in the LP creation path.
- Impact: Users can receive more or fewer LP shares than their economic contribution warrants. A depositor can favor the over-rewarded side and dilute other onboarding participants.

## Nominal deposit accounting overcredits fee-on-transfer tokens
- Location: `src/DegenBox.sol` : `deposit`; `src/blast/BlastOnboarding.sol` : `deposit`
- Mechanism: Both deposit paths credit the requested `amount` rather than measuring the actual token balance delta received. For fee-on-transfer or deflationary tokens, the contract receives less than `amount` while recording the full amount in user/internal accounting.
- Impact: If such a token is enabled/supported, an attacker can deposit at a transfer-fee discount, receive full credit, and withdraw against the shared pool, draining other users of the same token and leaving the system undercollateralized.

