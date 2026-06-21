# Audit: 2026-01-tempo-feeamm
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Reentrancy / CEI violation in `burn` (token transfers before all state updates)
*(consensus, 6 of 6 reports)*
- Location: contracts/FeeAMM.sol : `burn` (the `IERC20(userToken).transfer` / `IERC20(validatorToken).transfer` calls precede the `liquidityBalances[poolId][msg.sender] -=`, `totalSupply[poolId] -=`, and `pool.reserve* -=` writes)
- Mechanism: `burn` computes the payout and performs both outbound token transfers to the caller-chosen `to` *before* decrementing the LP balance, total supply, and both reserves. There is no `nonReentrant` guard. The top-of-function check `liquidityBalances[poolId][msg.sender] < liquidity` and the reserve reads inside `_calculateBurnAmounts` all evaluate against un-decremented state during the transfer callback. Since pool creation and token addresses are permissionless, a token with a transfer/receive hook (ERC-777-style, ERC-1363, malicious/upgradeable ERC-20) lets the recipient re-enter `burn` (or cross-function into `executeFeeSwap`/`rebalanceSwap`/`mint`) with the same `liquidity`; the check passes again and the same claim is paid repeatedly.
- Impact: An attacker drains the pool's reserves far beyond their share, stealing other LPs' funds; because token custody is shared across pools, the theft can be cross-pool. As recursion unwinds, the repeated `-=` operations underflow under the `<0.8.0` pragma and wrap to ~2^256, corrupting accounting and leaving effectively unlimited future burn capacity — total loss of deposited funds.

## Missing cumulative `uint128` overflow guard on reserve increments
*(consensus, 6 of 6 reports)*
- Location: contracts/FeeAMM.sol : `executeFeeSwap` (`pool.reserveUserToken += uint128(amountIn)`) and `mint` (`pool.reserveValidatorToken += uint128(amountValidatorToken)`)
- Mechanism: `_requireU128` only validates that the *single added amount* fits in `uint128`; it never checks that `existingReserve + amount` fits. Under the `<0.8.0` pragma `uint128 += uint128` wraps silently. `rebalanceSwap` explicitly guards exactly this (`if (uint256(pool.reserveValidatorToken) + amountIn > type(uint128).max) revert`), but `executeFeeSwap` and `mint` perform the symmetric increment with no such check — an internally inconsistent, asymmetric omission.
- Impact: If a reserve approaches `type(uint128).max` (~3.4e38 base units), the next deposit/swap wraps the stored reserve to a tiny value while real token balances are unchanged, corrupting all subsequent share/burn/liquidity math (zeroing the recorded reserve, enabling unfair issuance/withdrawal, or bricking/locking the pool). Practical reachability is low for normal stablecoin supplies but the guard is genuinely missing.
- Reviewer disagreement: reports diverge on severity — some call it a real fund-loss primitive, others rate practical exploitability low because the magnitude required is unrealistic.

## Reentrancy in `executeFeeSwap` (inbound `transferFrom` before reserve update)
*(consensus, 5 of 6 reports)*
- Location: contracts/FeeAMM.sol : `executeFeeSwap` (the `IERC20(userToken).transferFrom(...)` precedes `pool.reserveUserToken += ...` / `pool.reserveValidatorToken -= ...`)
- Mechanism: The liquidity check `require(pool.reserveValidatorToken >= amountOut)` runs *before* `transferFrom`, and the reserve updates run *after* it. A `userToken` with a sender-side hook (ERC-777 `tokensToSend`, fired on `msg.sender` during `transferFrom`) lets the attacker re-enter `executeFeeSwap` while `reserveValidatorToken` is still at its pre-swap value, so the same reserve passes the `>= amountOut` check in each nested call. Permissionless pool creation lets the attacker introduce the hookable token.
- Impact: The attacker withdraws more `validatorToken` than the reserve supports across nested swaps; the later `pool.reserveValidatorToken -= uint128(amountOut)` underflows and wraps near `type(uint128).max`, poisoning all downstream computations (burn payouts, mint share price) and enabling further drains of validator-token balances held by the contract.
- Reviewer disagreement: one report (opus-4-8 shot 3) rates this lower severity than the `burn` case because the out-transfer in `executeFeeSwap` is correctly placed after the reserve write.

## Unchecked ERC-20 return values (no SafeERC20)
*(consensus, 5 of 6 reports)*
- Location: contracts/FeeAMM.sol : `executeFeeSwap`, `rebalanceSwap`, `mint`, `burn` — every `IERC20(...).transfer` / `transferFrom` call
- Mechanism: All token movements use raw `IERC20.transfer`/`transferFrom` and discard the boolean return; no pre/post balance check is performed. A token that returns `false` instead of reverting (or a fee-on-transfer / no-op token) lets execution proceed as if the full amount moved. In `executeFeeSwap`, a failing inbound `transferFrom` is still followed by `reserveUserToken += amountIn` and the outbound `validatorToken` payout; `mint`/`rebalanceSwap` credit reserves (and mint LP shares) for tokens never received; `burn` silently "succeeds" on failed payouts.
- Impact: With a non-reverting-on-failure token on the input side, an attacker calls `executeFeeSwap`/`rebalanceSwap`/`mint` without funding the pull and still receives the valuable paired token or LP shares — draining the opposite reserve for free or corrupting the accounting all share math depends on. Reachable because the AMM accepts arbitrary token addresses with no allowlist.

## mint/burn valuation asymmetry (mint undervalues the existing userToken reserve; burn redeems it at par)
*(consensus, 3 of 6 reports)*
- Location: contracts/FeeAMM.sol : `mint` (else branch: `product = (N * reserveUserToken) / SCALE; denom = reserveValidatorToken + product; liquidity = amountValidatorToken * totalSupply / denom`) vs. `_calculateBurnAmounts` / `burn`
- Mechanism: When minting into an existing pool, the userToken reserve is discounted to `N/SCALE` (0.9985) in the share denominator, so `denom = V + 0.9985·U` is strictly below the fair pool value `V + U` — the minter receives *more* shares than fair. But `burn` redeems each share for a full, undiscounted pro-rata slice of both reserves (`liquidity * reserveUserToken / totalSupply`). The discount is applied in the wrong direction: protecting existing LPs requires *over*-valuing existing assets at issuance, not under-valuing them. Net profit of a mint→burn cycle is `d·0.0015·U / (D + d)` with `D = V + 0.9985·U`.
- Impact: Any address (optionally flash-funded) can mint a large position and immediately burn it to skim value from existing LPs — converging to ~0.15% of the entire accumulated userToken reserve per pass, with no special token and no price movement. Atomic, repeatable theft from honest LPs; reports differ on whether it is a fast atomic drain or a bounded slow leak per transaction.

## Minority findings

## `rebalanceSwap` mispricing — sells userToken below par, leaking value to the caller
*(minority, 1 of 6 reports)* *(conflicting reviews: 1 of 6 reports treated this same discount as an intended rebate, not a bug)*
- Location: contracts/FeeAMM.sol : `rebalanceSwap`, line `amountIn = (amountOut * N) / SCALE + 1;`
- Mechanism: The fee multiplier `N = 9985` is applied as a *multiplier on the output* instead of a divisor, so to receive `amountOut` of `userToken` the caller pays only `amountIn ≈ amountOut * 0.9985`. With reserves moving `reserveValidatorToken += amountIn`, `reserveUserToken -= amountOut`, the pool's value change is `−0.0015·amountOut` — it loses 0.15% on every call (versus `executeFeeSwap`, which correctly gains 0.30%). A correct fee would charge above par, e.g. `amountIn = amountOut * SCALE / N + 1`.
- Impact: Because both legs are par USD stablecoins, any caller buys `userToken` at a guaranteed 0.15% discount and realizes it as risk-free profit against par/external markets, draining up to the entire `reserveUserToken` of any pool. No imbalance condition gates the discount, and fee swaps continuously replenish `reserveUserToken`, so the leak is always exploitable and repeatable.
- Reviewer disagreement: opus-4-8 shot 3 describes the identical discount as an intended "rebalance rebate" paid to rebalancers (by-design incentive), whereas this report classifies it as a mispricing bug that leaks LP value.

## Fixed-rate swaps with no oracle — a depeg drains the higher-value side
*(minority, 1 of 6 reports)*
- Location: contracts/FeeAMM.sol : `executeFeeSwap` (`amountOut = amountIn * M / SCALE`) and `rebalanceSwap` (`amountIn = amountOut * N / SCALE + 1`)
- Mechanism: Both swap paths use a hard-coded constant rate (0.997 / 0.9985) that assumes each token is permanently worth exactly $1. There is no price oracle, no freshness check, and no circuit breaker; the rate is independent of reserve ratio or any external price, and both functions are callable by anyone.
- Impact: If `userToken` depegs (e.g. to $0.50), an arbitrageur buys it cheaply on the open market and feeds it into `executeFeeSwap`, receiving ~$1 of `validatorToken` per unit and draining the validatorToken reserve at large profit; a `validatorToken` depeg is exploited symmetrically via `rebalanceSwap`. Loss is borne entirely by LPs. (The report notes this is the standard fixed-rate-AMM trust assumption, but flags that nothing here mitigates it — no pause, per-token cap, or oracle.)

## `checkSufficientLiquidity` — unbounded `maxAmount * M` multiply can silently overflow
*(minority, 1 of 6 reports)*
- Location: contracts/FeeAMM.sol : `checkSufficientLiquidity`
- Mechanism: The view computes `maxAmount * M` on an unbounded `uint256` with no size check. Under the `<0.8.0` pragma this multiply wraps silently for a large `maxAmount`, so the function can compute a small wrapped product and report "sufficient" liquidity when there is none.
- Impact: Integrators relying on `checkSufficientLiquidity` as a pre-flight check can be misled into believing a swap is backed when it is not, leading to failed or mispriced downstream interactions. (Raised as a secondary observation distinct from the reserve-increment overflow.)

## `mint` — `amountValidatorToken * _totalSupply` is an unbounded `uint256` multiply computed before `_requireU128`
*(minority, 1 of 6 reports)*
- Location: contracts/FeeAMM.sol : `mint` (share computation `liquidity = amountValidatorToken * _totalSupply / denom`)
- Mechanism: The product `amountValidatorToken * _totalSupply` is evaluated *before* `_requireU128(amountValidatorToken)` runs, so the share calculation relies on an unbounded `uint256` multiply not overflowing. Under the `<0.8.0` pragma there is no automatic overflow check on this intermediate product.
- Impact: A sufficiently large `amountValidatorToken` combined with a large `_totalSupply` can overflow the intermediate multiply before the bound is enforced, producing a wrapped (and wrong) `liquidity` share amount and corrupting LP issuance accounting.

---

*Self-check: 9 distinct findings identified across the 6 input reports (burn reentrancy; cumulative uint128 reserve-increment overflow; executeFeeSwap reentrancy; unchecked ERC-20 return values; mint/burn valuation asymmetry; rebalanceSwap mispricing; fixed-rate/no-oracle depeg; checkSufficientLiquidity overflow; mint unbounded uint256 multiply). 9 findings emitted — none dropped.*

