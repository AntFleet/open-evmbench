# Audit: 2024-03-abracadabra-money

## Cauldron `cook` can skip solvency checks
- Location: `src/cauldrons/CauldronV4.sol` : `cook`
- Mechanism: `cook` sets `status.needsSolvencyCheck = true` after `ACTION_BORROW` and `ACTION_REMOVE_COLLATERAL`, but any later unhandled action falls into `_additionalCookAction`; the base implementation returns a default empty `CookStatus`, and `cook` overwrites `status` with it. Appending an unhandled action such as `ACTION_ACCRUE` clears the pending final solvency check.
- Impact: An attacker can borrow MIM or remove collateral through `cook` and finish insolvent, draining available cauldron liquidity.

## Flash-loan fees are left as skimmable surplus
- Location: `src/DegenBox.sol` : `flashLoan`, `batchFlashLoan`, `deposit`
- Mechanism: Flash loans require repayment of `amount + fee`, but the fee is only checked against `totals[token].addElastic(fee)` and is not persisted into `totals[token].elastic`. The extra repaid tokens remain unaccounted vault surplus, and `deposit(..., from = address(this), ...)` intentionally lets anyone skim surplus into shares. In `batchFlashLoan`, repeated entries for the same token are checked per entry against unchanged totals, not against aggregate fees.
- Impact: Attackers can steal flash-loan fees owed to depositors and can underpay fees in duplicate-token batch flash loans.

## MagicLP TWAP can be retroactively manipulated
- Location: `src/mimswap/MagicLP.sol` : `_setReserve`, `_resetTargetAndReserve`, `_sync`, `_twapUpdate`
- Mechanism: Reserve-changing functions update `_BASE_RESERVE_` / `_QUOTE_RESERVE_` before calling `_twapUpdate()`. `_twapUpdate()` then adds `getMidPrice() * timeElapsed`, so the new attacker-manipulated reserves are treated as if they existed for the entire elapsed interval.
- Impact: An attacker can manipulate `_BASE_PRICE_CUMULATIVE_LAST_` immediately before a TWAP consumer reads it, causing downstream pricing, trading, or liquidation logic to use an attacker-controlled TWAP.

## Initial MagicLP liquidity can break the configured `I` ratio
- Location: `src/mimswap/MagicLP.sol` : `buyShares`
- Mechanism: Initial share minting checks quote sufficiency using `DecimalMath.mulFloor(baseBalance, _I_)`. Flooring can make an insufficient quote amount appear sufficient, causing `shares = baseBalance` and targets to be initialized with a materially wrong `_BASE_TARGET_ / _QUOTE_TARGET_` ratio.
- Impact: An attacker can create a factory-listed pool whose actual pricing invariant differs from the advertised `I`, causing traders to receive malicious prices and lose funds.

## Imbalanced pool creation leaves exploitable reserve/target mismatch
- Location: `src/blast/BlastOnboardingBoot.sol` : `bootstrap`; `src/mimswap/periphery/Router.sol` : `createPool`; `src/mimswap/MagicLP.sol` : `buyShares`
- Mechanism: `bootstrap()` and `Router.createPool()` transfer all supplied base and quote tokens to the pool, but initial `buyShares()` sets targets from the limiting side while reserves include all transferred tokens. If the supplied amounts are not exactly at the intended ratio, `_RState_` starts as `ONE` even though reserves and targets are inconsistent.
- Impact: Attackers can trade against the malformed PMM state and extract value from the bootstrapped liquidity, causing losses to onboarding depositors or first LPs.

## LP oracle returns zero reserves
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `_getReserves`, `latestAnswer`
- Mechanism: `_getReserves()` declares return values but only assigns `pair.getReserves()` to local variables and never returns them. `latestAnswer()` therefore receives `(0, 0)` and computes an LP price of zero.
- Impact: Any market using this aggregator receives a broken LP price, which can brick borrowing/liquidation flows or corrupt solvency checks depending on the downstream oracle adapter.

## LP oracle uses manipulable spot reserves
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `latestAnswer`
- Mechanism: In the intended reserve-returning implementation path, `latestAnswer()` values LP tokens from current pool reserves and `totalSupply()` without checking the pool price against external base/quote oracle prices or any manipulation-resistant invariant. Current reserves can be changed in the same transaction.
- Impact: An attacker can flash-manipulate reserves to inflate LP collateral value and over-borrow, or deflate it to trigger unfair liquidations.

## Oracle feed answers are accepted without validity checks
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `latestAnswer`, `latestRoundData`
- Mechanism: The aggregator casts `baseOracle.latestAnswer()` and `quoteOracle.latestAnswer()` directly from `int256` to `uint256` without requiring positive answers, freshness, or completed rounds. Its own `latestRoundData()` returns zero timestamps and round ids.
- Impact: Stale, negative, or incomplete underlying feed data can produce invalid LP prices, enabling bad borrows, bad liquidations, or oracle-consumer DoS.

## Fee-on-transfer tokens are overcredited
- Location: `src/DegenBox.sol` : `deposit`; `src/blast/BlastOnboarding.sol` : `deposit`
- Mechanism: Both deposit paths credit the requested `amount` before/after `safeTransferFrom` without measuring the actual balance delta received. Fee-on-transfer or deflationary tokens therefore create internal balances larger than real token holdings.
- Impact: If such a token is accepted/enabled, attackers can deposit taxed tokens, receive full credit, and withdraw or claim value funded by honest users.

## Fee cap check validates the old fee
- Location: `src/mixins/FeeCollectable.sol` : `setFeeParameters`
- Mechanism: The guard checks `feeBips > BIPS` instead of `_feeBips > BIPS`, so a valid current fee allows writing any new `uint16` fee, including values above 100%.
- Impact: A fee operator in any inheriting contract can set confiscatory or underflowing fees, bricking fee-bearing flows or taking more than the intended maximum.

