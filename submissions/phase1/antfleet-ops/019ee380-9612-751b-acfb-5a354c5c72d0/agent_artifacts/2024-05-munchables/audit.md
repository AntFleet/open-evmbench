# Audit: 2024-05-munchables

Below are the genuine security vulnerabilities I found, ordered roughly by severity.

## Schnibbles reward is over-scaled by 1e18 on every pet
- Location: `src/managers/SnuggeryManager.sol` : `pet`
- Mechanism: `PET_TOTAL_SCHNIBBLES` is configured already in 1e18-fixed-point units (the comment says `10e18 / 72`). The petting payout then multiplies by `1e18` a *second* time: `petterSchnibbles = ((totalSchnibbles * 5) / 11) * 1e18;` and `pettedSchnibbles = ((totalSchnibbles * 6) / 11) * 1e18;`. The trailing `* 1e18` should not be there — the values are inflated by a full 18 decimal places (a ~10–11 schnibble payout becomes ~6e34).
- Impact: Each pet credits both the petter and the petted account astronomically more `unfedSchnibbles` than intended. Petting is permissionless (any registered account can pet any other registered account's munchable subject only to 5-/10-minute cooldowns). An attacker can mint effectively unlimited schnibbles, feed them into NFT chonks / claim points, and ultimately convert to MUNCH tokens via `ClaimManager.convertPointsToTokens`, draining the entire token economy.

## Migration harvest bonus is unbounded near the upper threshold
- Location: `src/managers/BonusManager.sol` : `_calculateMigrationBonus`
- Mechanism: When `halfAmount <= weightedValue < migrateHighestAmount`, the bonus is computed as `migrationBonus * (weightedValue - halfAmount) / (migrateHighestAmount - weightedValue)`. The denominator uses `(migrateHighestAmount - weightedValue)`, which tends to zero as `weightedValue` approaches `migrateHighestAmount`. The interpolation denominator was clearly intended to be the fixed range `(migrateHighestAmount - halfAmount)`. As written the bonus grows without bound and far exceeds the supposed maximum `migrationBonus`.
- Impact: A migrated user can tune their locked weighted value to sit just below `migrateHighestAmount` and obtain an arbitrarily large harvest multiplier in `getHarvestBonus`, which `AccountManager._harvest` applies as `dailySchnibbles += (dailySchnibbles * bonus) / 1e18`. This lets the user mint vastly more schnibbles than any legitimate cap permits.

## WETH yield is claimed using the USDB token address
- Location: `src/managers/RewardsManager.sol` : `_claimYieldForContract`
- Mechanism: After computing the WETH claimable amount (`_yieldWETH = IERC20Rebasing(address(WETH)).getClaimableAmount(_contract)`), the code calls `IERC20YieldClaimable(_contract).claimERC20Yield(address(USDB), _yieldWETH)` — passing the **USDB** contract address with the **WETH** amount (copy-paste of the USDB branch). The downstream `claimERC20Yield` therefore calls `IERC20Rebasing(USDB).claim(rewardsManager, _yieldWETH)`.
- Impact: WETH yield is never actually claimed; instead an arbitrary WETH-sized amount is claimed against the USDB rebasing token. This corrupts yield accounting — WETH yield is stranded while USDB claims are made for the wrong magnitude, and the `YieldClaimedForContract` event reports a WETH figure that was never collected. Real value is mis-distributed/lost relative to the intended split.

## Signature recovery guard is inverted and always reverts
- Location: `src/libraries/SignatureVerifier.sol` : `recover`
- Mechanism: The validity check is `if (v != 27 || v != 28) revert InvalidSignature();`. For any `v`, one of the two disjuncts is always true (a single value cannot equal both 27 and 28), so the condition is always satisfied and the function unconditionally reverts. The intended check was `v != 27 && v != 28`. Additionally there is no zero-address check on the `ecrecover` result and no `s`-malleability bound.
- Impact: Any code path relying on this verifier is permanently broken (DoS); and if the operator "fixes" only the `||`/`&&` typo, the remaining missing zero-address / malleability checks would allow `ecrecover` to silently return `address(0)` on malformed signatures and accept two signatures per message. Because signature-gated reveals/mints depend on correct recovery, this is a correctness/auth hazard.

## Permissionless yield/gas claiming for arbitrary contracts
- Location: `src/managers/RewardsManager.sol` : `claimYieldForContracts`, `claimGasFeeForContracts`
- Mechanism: Both functions are externally callable with no role check, taking a caller-supplied `_contracts` array. They invoke `blastContract.claimAllYield(_contract, address(this))` / `claimMaxGas(...)` and, for each contract, call back into `IERC20YieldClaimable(_contract).claimERC20Yield(...)`. The (commented-out) original versions were `onlyRole(Role.ClaimYield)`; the live replacements dropped the guard.
- Impact: Anyone can force-claim yield and gas for any contract at any time and route arbitrary `_contract` addresses through the rewards pipeline (the yield is pushed to the configured distributors/treasury, and the callback is made under the RewardsManager's authority). At minimum this is an unauthorized state-change / griefing primitive (forcing premature claims, interfering with accounting and the WETH/USDB bug above); combined with the mis-addressed claim it amplifies the accounting corruption.

