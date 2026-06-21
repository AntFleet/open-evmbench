# Audit: 2024-03-abracadabra-money

# Open EVMBench Detect Audit — Abracadabra Money (2024-03)

## MagicLpAggregator never returns pool reserves
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `_getReserves`
- Mechanism: `_getReserves()` calls `pair.getReserves()` into locals but never returns them. `latestAnswer()` then destructures `(baseReserve, quoteReserve)` from that helper and uses them in `minAnswer * (baseReserve + quoteReserve) / pair.totalSupply()`. With zero reserves, the reported LP price is always `0`.
- Impact: Any Cauldron or pricing path relying on this aggregator gets a zero exchange rate. Insolvent positions can appear solvent (`borrow * 0 = 0`), blocking liquidations and allowing undercollateralized borrowing/bad debt. Alternatively, integrations that reject a zero rate can be bricked.

## FeeCollectable validates the wrong fee variable
- Location: `src/mixins/FeeCollectable.sol` : `setFeeParameters`
- Mechanism: `setFeeParameters` checks `if (feeBips > BIPS)` instead of validating the incoming `_feeBips`. The old stored value is checked; the new value is written unconditionally.
- Impact: A fee operator can set `feeBips` above 10_000 (100%). `calculateFees()` then computes `feeAmount = amountIn * feeBips / BIPS`, which can exceed `amountIn` and underflow `userAmount = amountIn - feeAmount`, reverting fee-taking flows or allowing misconfigured fee extraction depending on call path.

## Blast onboarding claims ignore token value parity
- Location: `src/blast/BlastOnboardingBoot.sol` : `_claimable`
- Mechanism: Claimable staking shares are allocated as `(userLocked * totalPoolShares) / totalLocked`, where `userLocked` and `totalLocked` are raw token amounts summed across MIM and USDB (`balances[user][MIM].locked + balances[user][USDB].locked`). The formula treats 1 MIM and 1 USDB as equal regardless of market value or depeg.
- Impact: If the tokens diverge in price before bootstrap, an attacker can lock only the cheaper token and receive the same share count as users who locked equal nominal amounts of the more valuable token. That yields an unfairly large share of bootstrapped LP/staking rewards at others’ expense.

## MagicLpAggregator LP price is manipulable via permissionless reserve updates
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `latestAnswer` (with `src/mimswap/MagicLP.sol` : `sync`)
- Mechanism: Even when reserves are returned correctly, `latestAnswer()` prices LP tokens from spot `baseReserve + quoteReserve` (normalized and summed). `MagicLP.sync()` is permissionless and updates reserves to the contract’s current token balances without minting/burning LP shares. An attacker can donate tokens to the pool and call `sync()` to inflate reserves without increasing `totalSupply()`.
- Impact: An attacker holding (or about to use) MagicLP tokens as collateral can temporarily inflate the oracle price, borrow excess MIM from a Cauldron, and leave the protocol with bad debt once the donation is arbitraged away or the price normalizes.

## MagicLpAggregator does not validate negative oracle answers
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `latestAnswer`
- Mechanism: `baseOracle.latestAnswer()` and `quoteOracle.latestAnswer()` are cast directly with `uint256(...)`. A negative `int256` answer wraps to a very large unsigned value before normalization.
- Impact: A misconfigured, malfunctioning, or malicious underlying aggregator can push an astronomically high LP price through `latestAnswer()`, enabling massive overborrowing against LP collateral in any Cauldron wired to this oracle.

## BlastOnboarding deposit is vulnerable to reentrancy before accounting
- Location: `src/blast/BlastOnboarding.sol` : `deposit`
- Mechanism: `deposit()` performs `token.safeTransferFrom(...)` before updating `balances`, `totals`, and cap checks. A token with transfer hooks (ERC777-style) can reenter `deposit`, `lock`, or `withdraw` while the outer call’s accounting is incomplete.
- Impact: With a callback-enabled token listed as supported, an attacker can reenter during `transferFrom` and corrupt onboarding accounting (double-counting deposits, bypassing caps, or withdrawing before balances are updated), potentially draining pooled funds or breaking bootstrap invariants.

