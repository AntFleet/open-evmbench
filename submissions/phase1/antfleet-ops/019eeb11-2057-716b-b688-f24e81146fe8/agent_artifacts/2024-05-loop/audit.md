# Audit: 2024-05-loop
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Token claim credits the entire contract ETH balance instead of the swap proceeds
*(consensus, 6 of 6 reports)*
- Location: `src/PrelaunchPoints.sol` : `_claim` (non-ETH/`else` branch) together with `_fillQuote` and `receive()`
- Mechanism: After swapping the staker's LRT to ETH, `_claim` sets `claimedAmount = address(this).balance` and mints lpETH for the contract's *entire* ETH balance rather than the delta produced by that user's own swap. `_fillQuote` already computes the correct bought amount (`boughtETHAmount = address(this).balance - balanceBefore`) but only emits it in `SwappedTokens` and discards the value. Because `receive()` is public (and the NatSpec wrongly promises directly-sent ETH is "locked forever"), any ETH resident in the contract — donations, forced/misdirected sends, swap/0x dust, or deposit-cap refunds from `convertAllETH` — is creditable.
- Impact: Any user with a positive balance of an allowed non-ETH token can `claim`/`claimAndStake` (a tiny `_percentage`, or potentially a zero/dust amount if a zero-sell 0x quote succeeds, leaving most of their tokens intact to repeat) and sweep all stray ETH in the contract into their own lpETH balance. This front-runnable theft breaks the documented "locked forever" invariant and lets a single token-claimer siphon ETH that belongs to no one or to the ETH-staker pool. Fix: credit `boughtETHAmount` returned from `_fillQuote`, not `address(this).balance`.

## No minimum-output (slippage) floor enforced on the claim swap
*(consensus, 2 of 6 reports)*
- Location: `src/PrelaunchPoints.sol` : `_validateData` (and `_decodeUniswapV3Data` / `_decodeTransformERC20Data`), invoked from `_claim`
- Mechanism: `_validateData` checks the selector, input/output token, exact `inputTokenAmount`, and (UniswapV3 only) recipient, but never reads or constrains the minimum-output field — `minBuyAmount` for `sellTokenForEthToUniswapV3` (calldata [68..100), skipped between `sellAmount` and `recipient`) or `minOutputTokenAmount` for `transformERC20` (calldata [100..132), past the last field the decoder reads). The swap therefore executes with whatever floor (including zero) is embedded in user-supplied calldata, and the contract then accepts whatever ETH results via the `address(this).balance` read above without ever reverting on a bad fill.
- Impact: A pooled-fund-custodying contract enforces no slippage defense-in-depth on conversion. A claim sitting in the mempool with a loose, stale, or zero `minBuyAmount` can be sandwiched/MEV'd, converting the staker's LRT into materially less lpETH with no on-chain protection. Severity is bounded by the caller supplying their own calldata, but the gap is real whenever the supplied minimum is stale or zero.

## `setOwner` accepts `address(0)`, permanently disabling conversion / access
*(consensus, 2 of 6 reports)*
- Location: `src/PrelaunchPoints.sol` : `setOwner`
- Mechanism: `setOwner` performs no zero/sanity check (`owner = _owner;`). Setting `owner = address(0)` (or any wrong address) is irreversible because every recovery path — `setOwner`, `setLoopAddresses`, `convertAllETH`, `setEmergencyMode`, `allowToken`, `recoverERC20` — is gated by `onlyAuthorized`.
- Impact: If `owner` is zeroed before `convertAllETH` is called, `startClaimDate` can never be set, bricking the lpETH conversion and all `claim`/`claimAndStake` flows forever. Locked ETH remains withdrawable through the open `withdraw` window, so this is a liveness/funds-lockup risk on the lpETH side rather than outright theft. Within the trusted-owner model, but worth a zero-address guard.

## Fee-on-transfer / rebasing allowed tokens overcredit balances
*(consensus, 2 of 6 reports)*
- Location: `src/PrelaunchPoints.sol` : `_processLock`, `allowToken`, `withdraw` (and non-ETH `_claim`)
- Mechanism: For allowed non-WETH ERC20 tokens, `_processLock` credits `balances[_receiver][_token] += _amount` after `safeTransferFrom` without measuring the actual balance increase. A fee-on-transfer, deflationary, burn-on-transfer, or negatively-rebasing token can transfer less than `_amount` while the full `_amount` is recorded.
- Impact: If the owner allows such a token, an attacker can deposit an amount that credits more than the contract receives, then `withdraw` or `claim` against the inflated recorded balance — draining same-token deposits supplied by other users, or causing insolvency/DoS for later withdrawals and claims. Preconditions: such a token is in `_allowedTokens` or added via `allowToken` (or an allowed token later becomes fee-charging/upgraded).

## Minority findings

## Fixed-offset 0x calldata decoding can diverge from the executed swap; `transformations[]` never validated
*(minority, 1 of 6 reports)* *(conflicting reviews: 2 of 6 reports defended this code path)*
- Location: `src/PrelaunchPoints.sol` : `_decodeUniswapV3Data`, `_decodeTransformERC20Data`, `_validateData`
- Mechanism: The decoders read fields from *fixed* calldata offsets via `calldataload`, but the real 0x functions read their dynamic members (`encodedPath` for UniswapV3, the `transformations[]` array for `transformERC20`) through the ABI offset word at calldata position 4. A caller can place validation-passing data at the fixed offsets while pointing the dynamic offset word elsewhere, so the path/transformations actually executed are not the ones the contract validated; the `transformations[]` array is never validated at all.
- Impact: The token/path guarantees the contract appears to enforce can be partially evaded for the dynamic components, compounding the absent slippage floor and the `address(this).balance` read. Cross-user theft is bounded (allowance in `_fillQuote` is set to exactly `_amount`, proceeds go to the claimer), but it is a per-claim value-extraction surface relying on unverified dynamic data.
- Reviewer disagreement: Two other reports concluded the assembly offsets are correct and that 0x's own semantics force the pulled token, amount (≤ the caller's own balance), and recipient to match the validated values, so the swap "cannot be redirected to a different token, amount, or recipient."

## `_percentage` is an unbounded `uint8`
*(minority, 1 of 6 reports)*
- Location: `src/PrelaunchPoints.sol` : `_claim` — `uint256 userClaim = userStake * _percentage / 100; balances[msg.sender][_token] = userStake - userClaim;`
- Mechanism: `_percentage` is accepted as any `uint8` (0–255) with no `<= 100` bound. For values 101–255, `userClaim` exceeds `userStake`, so `userStake - userClaim` underflows and reverts under 0.8.x checked math. No earlier validation rejects the bad input.
- Impact: Low — a caller supplying a percentage above 100 only reverts their own claim; no state corruption and no effect on other users. Worth tightening with `require(_percentage <= 100)` so the parameter cannot silently produce a `userClaim` larger than the stake.

## `setLoopAddresses` accepts a zero / non-contract address (one-shot, irreversible)
*(minority, 1 of 6 reports)* *(conflicting reviews: 1 of 6 reports defended this code path)*
- Location: `src/PrelaunchPoints.sol` : `setLoopAddresses`
- Mechanism: `setLoopAddresses` performs no zero-address or `code.length > 0` check on `_loopAddress` / `_vaultAddress`. Because it is one-shot and gated by `onlyBeforeDate(loopActivation)`, a bad value can never be corrected.
- Impact: Low/operational. If `lpETH` is set to a zero/invalid address, `convertAllETH` and all `claim` paths brick; user ETH is still withdrawable via `withdraw` (startClaimDate stays at its max sentinel), but the protocol is left unrecoverable. Add zero-address and contract-code guards.
- Reviewer disagreement: One other report classified this as "owner-only and within the trusted-owner model," i.e. not a vulnerability.

## Unaccounted ETH is distributed pro rata to ETH lockers
*(minority, 1 of 6 reports)* *(conflicting reviews: 2 of 6 reports defended this code path)*
- Location: `src/PrelaunchPoints.sol` : `_processLock`, `convertAllETH`, `_claim` (ETH branch), `receive()`
- Mechanism: `totalSupply` tracks only ETH/WETH locked through `_processLock`, but `convertAllETH` deposits `address(this).balance` — including ETH sent directly to `receive()` or forced into the contract — and then sets `totalLpETH = lpETH.balanceOf(...)`. ETH claims pay `userStake * totalLpETH / totalSupply`, so any unaccounted ETH present before conversion inflates `totalLpETH` without being reflected in `totalSupply`.
- Impact: Accidental direct/forced ETH transfers are converted and paid out pro rata to ETH lockers even though that ETH was never accounted to its sender; a small ETH locker captures a proportional share of all such unaccounted ETH.
- Reviewer disagreement: Two other reports examined the ETH proportional-claim math and deemed it sound — `totalSupply`/`totalLpETH` are frozen at conversion, `userStake.mulDiv(totalLpETH, totalSupply)` distributes exactly `totalLpETH` with floor rounding favoring the protocol, and the sum of claims ≤ `totalLpETH` (no insolvency or first-depositor/dilution exploit).

---

*Reconciliation: 8 distinct findings identified across the 6 input reports (by code path + root cause); 8 findings emitted (4 consensus, 4 minority). No findings dropped.*

